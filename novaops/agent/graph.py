"""The agent graph: one loop, two scopes (Maya, Webex).

    START -> classify -> scope -> answer --(tool calls)--> tools --> answer
                                      |  no tool calls, but the plan needed a lookup
                                      +--> rearm (once) --> answer
                                      +--> END

  classify  planner model call -> TurnPlan (intent, facts, constraints)
  scope     plain code: intent -> visible read tools, plus write_gate.released_writes()
  answer    the answer model, bound to ONLY this turn's tools
  tools     executes calls; fills caller_id itself; refuses tools that were not visible
  rearm     Lesson 10's recovery when a narrow loadout left the model without a lookup

State is checkpointed per thread (SQLite in run.py), so a conversation survives a
restart of the process. Node names are the Langfuse span names a reviewer clicks
through: classify -> scope -> answer -> tools -> answer (Lesson 11: the Langfuse
callback is bound to the compiled graph, so every caller is traced).
"""
import copy
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langfuse.langchain import CallbackHandler

from .. import llm
from . import policy, write_gate

KEEP_TURNS = 2   # verbatim user turns the answer model sees (Lesson 10 stage 2)


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    caller_id: str          # application input — never inferred by the model
    caller_group: str       # application input
    plan: dict
    scope: str              # "maya" | "webex"
    loadout: list[str]      # tools visible this turn
    rearmed: bool


def model_schema(tool) -> dict:
    """The tool's schema as the MODEL sees it: `caller_id` removed for caller-scoped
    tools, so the model cannot even express a different caller."""
    schema = copy.deepcopy(convert_to_openai_tool(tool))
    if tool.name in policy.CALLER_TOOLS:
        params = schema["function"]["parameters"]
        params.get("properties", {}).pop("caller_id", None)
        if "caller_id" in params.get("required", []):
            params["required"].remove("caller_id")
    return schema


def current_turn(messages: list) -> list:
    starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    return messages[starts[-1]:] if starts else messages


def window(messages: list, keep: int = KEEP_TURNS) -> list:
    """Last `keep` user turns; tool traffic kept only for the current turn."""
    starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if not starts:
        return list(messages)
    turn_start = starts[-1]
    begin = starts[-keep] if len(starts) >= keep else starts[0]
    older = [m for m in messages[begin:turn_start]
             if not isinstance(m, ToolMessage) and not getattr(m, "tool_calls", None)]
    return older + list(messages[turn_start:])


def build_graph(tools: list, checkpointer=None):
    by_name = {t.name: t for t in tools}
    read_tools = sorted(n for n in by_name if n not in write_gate.WRITE_TOOLS)
    schemas = {n: model_schema(t) for n, t in by_name.items()}
    planner = llm.chat_model().with_structured_output(policy.TurnPlan)
    base_model = llm.chat_model()
    bound: dict[tuple, object] = {}

    def model_for(names: list[str]):
        key = tuple(sorted(names))
        if key not in bound:
            bound[key] = base_model.bind_tools([schemas[n] for n in key]) if key else base_model
        return bound[key]

    async def classify(state: AgentState) -> dict:
        try:
            plan = await planner.ainvoke(policy.planner_messages(state["messages"]))
        except Exception:                     # a planner failure must not stop the turn
            plan = None
        plan = plan or policy.TurnPlan(current_intent="other", requires_tools=True)
        return {"plan": plan.model_dump()}

    def scope(state: AgentState) -> dict:
        has_evidence = any(isinstance(m, ToolMessage) for m in state["messages"])
        plan = policy.enforce_evidence(policy.TurnPlan(**state["plan"]), has_evidence)
        loadout = policy.select_tools(plan, read_tools) + write_gate.released_writes(approval=None)
        return {"plan": plan.model_dump(), "loadout": loadout,
                "scope": policy.SCOPES[plan.current_intent], "rearmed": False}

    async def call_model(state: AgentState) -> dict:
        plan = policy.TurnPlan(**state["plan"])
        system = policy.ANSWER_PROMPT.format(
            caller_id=state["caller_id"], caller_group=state["caller_group"]) + policy.render_plan(plan)
        response = await model_for(state["loadout"]).ainvoke(
            [SystemMessage(system), *window(state["messages"])])
        return {"messages": [response]}

    async def run_tools(state: AgentState) -> dict:
        results = []
        for call in state["messages"][-1].tool_calls:
            if call["name"] not in state["loadout"]:
                results.append(ToolMessage(
                    f"Tool {call['name']!r} is not available for this request.",
                    tool_call_id=call["id"], name=call["name"], status="error"))
                continue
            args = dict(call["args"])
            if call["name"] in policy.CALLER_TOOLS:
                args["caller_id"] = state["caller_id"]     # application input, overrides the model
            try:
                results.append(await by_name[call["name"]].ainvoke(
                    {"name": call["name"], "args": args, "id": call["id"], "type": "tool_call"}))
            except Exception as exc:
                results.append(ToolMessage(f"Tool error: {exc}", tool_call_id=call["id"],
                                           name=call["name"], status="error"))
        return {"messages": results}

    def rearm(state: AgentState) -> dict:
        """The plan needed a lookup but the model answered without one: widen to every
        READ tool once and retry. Never widens to a write."""
        return {"loadout": read_tools, "rearmed": True,
                "messages": [RemoveMessage(id=state["messages"][-1].id)]}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        plan = policy.TurnPlan(**state["plan"])
        used_tool = any(isinstance(m, ToolMessage) for m in current_turn(state["messages"]))
        if plan.requires_tools and not state.get("rearmed") and not used_tool:
            return "rearm"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify)
    graph.add_node("scope", scope)
    graph.add_node("answer", call_model)
    graph.add_node("tools", run_tools)
    graph.add_node("rearm", rearm)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "scope")
    graph.add_edge("scope", "answer")
    graph.add_conditional_edges("answer", route, {"tools": "tools", "rearm": "rearm", END: END})
    graph.add_edge("tools", "answer")
    graph.add_edge("rearm", "answer")
    # Lesson 11: bind the Langfuse callback to the compiled graph — every node, Bedrock
    # call and MCP tool call becomes a span, for every caller. No keys -> a no-op.
    return graph.compile(checkpointer=checkpointer).with_config({"callbacks": [CallbackHandler()]})
