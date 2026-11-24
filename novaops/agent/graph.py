"""The agent graph: one loop, two scopes (Maya, Webex).

    START --(fresh history over threshold)--> distil --+
      |                                                v
      +--------------------------------------------> classify -> scope
                                                                  |
   action requested, or a diagnosed access request -> handoff -> END
   (run.py then starts the approval workflow, approval.py, on its own thread)
                                                                  |
                                               answer <-> tools (+ one rearm)
                                                  |
                         onboarding turn with evidence -> checklist -> END
                                                  +-> END

  distil     Lesson 10 stage 3: fold old history into named durable memory
  classify   planner model call -> TurnPlan (intent, facts, constraints, action_requested)
  scope      plain code: intent -> visible read tools (+ write_gate.released_writes())
  handoff    Maya proposes, never files: a typed AccessRequestIntent, status pending
  answer     the answer model, bound to ONLY this turn's tools
  tools      executes calls; fills caller_id itself; refuses tools that were not visible
  rearm      recovery when a narrow loadout left the model without a lookup
  recite     one rewrite when tools returned evidence but the answer cited none of it
  checklist  typed OnboardingChecklist, validated against the tool evidence

Node names are the Langfuse span names (the callback is bound to the compiled graph).
State is checkpointed per thread, so a conversation survives a process restart.
"""
import copy
from typing import Annotated, TypedDict

from langchain_core.messages import (AIMessage, HumanMessage, RemoveMessage, SystemMessage,
                                     ToolMessage)
from langchain_core.utils.function_calling import convert_to_openai_tool
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .. import config, llm
from . import approval, contracts, memory, policy, write_gate

KEEP_TURNS = 4           # verbatim user turns the answer model sees; 2 lost S1 t1's rule by t4 (#12)
EVIDENCE_CHARS = 12_000  # tool evidence handed to the checklist / handoff extractors


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    caller_id: str            # application input — never inferred by the model
    caller_group: str         # application input
    plan: dict
    scope: str                # "maya" | "webex"
    loadout: list[str]        # tools visible this turn
    rearmed: bool
    recite: bool              # this answer is a retry because the first draft cited nothing
    memory: dict              # durable distilled memory
    distilled_upto: int       # messages before this index are represented by memory
    handoff: dict | None      # AccessRequestIntent emitted THIS turn
    checklist: dict | None    # OnboardingChecklist produced THIS turn


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


def known_ids_text(messages: list) -> str:
    """Where an employee id may legitimately come from: a tool result or the user's words."""
    return "\n".join(str(m.content) for m in messages if isinstance(m, (ToolMessage, HumanMessage)))


def evidence(messages: list) -> str:
    """Everything tools returned in this conversation — the only admissible evidence."""
    return "\n".join(str(m.content) for m in messages if isinstance(m, ToolMessage))


def build_graph(tools: list, checkpointer=None):
    by_name = {t.name: t for t in tools}
    read_tools = sorted(n for n in by_name if n not in write_gate.WRITE_TOOLS | policy.APP_TOOLS)
    schemas = {n: model_schema(t) for n, t in by_name.items()}
    planner = llm.chat_model().with_structured_output(policy.TurnPlan)
    distiller = llm.chat_model().with_structured_output(memory.ConversationMemory)
    proposer = llm.chat_model().with_structured_output(contracts.AccessRequestProposal)
    checklister = llm.chat_model().with_structured_output(contracts.ChecklistProposal)
    base_model = llm.chat_model()
    bound: dict[tuple, object] = {}

    def model_for(names: list[str], force_tool: bool = False):
        """force_tool binds with Bedrock toolChoice=any: the model CANNOT answer without
        calling a tool. Measured: even with tools visible and a lookup required, Nova often
        answered from memory and invented content (docs/OBSTACLES.md #14)."""
        key = (tuple(sorted(names)), force_tool and bool(names))
        if key not in bound:
            tools_ = [schemas[n] for n in key[0]]
            bound[key] = (base_model.bind_tools(tools_, tool_choice="any") if key[1]
                          else base_model.bind_tools(tools_) if tools_ else base_model)
        return bound[key]

    def memory_text(state) -> str:
        return memory.render_memory(state["memory"]) if state.get("memory") else ""

    # --- distil -------------------------------------------------------------------
    def should_distil(state: AgentState) -> str:
        return "distil" if memory.needs_distillation(
            state["messages"][:-1], state.get("distilled_upto", 0), policy.render_transcript) else "classify"

    async def distil(state: AgentState) -> dict:
        upto = len(state["messages"]) - 1            # never distil the message being answered
        fresh = policy.render_transcript(state["messages"][state.get("distilled_upto", 0):upto])
        try:
            new = await distiller.ainvoke(memory.distiller_messages(state.get("memory") or {}, fresh))
        except Exception:
            new = None
        if not memory.memory_is_safe(state.get("memory") or {}, new):
            return {}                                 # rejected: raw history is kept, nothing lost
        return {"memory": new.model_dump(), "distilled_upto": upto}

    # --- classify / scope ---------------------------------------------------------
    async def classify(state: AgentState) -> dict:
        try:
            plan = await planner.ainvoke(policy.planner_messages(
                state["messages"], memory.render_memory(state.get("memory") or {}),
                state.get("distilled_upto", 0)))
        except Exception:                             # a planner failure must not stop the turn
            plan = None
        plan = plan or policy.TurnPlan(current_intent="other", request_type="lookup")
        return {"plan": plan.model_dump()}

    def scope(state: AgentState) -> dict:
        has_evidence = any(isinstance(m, ToolMessage) for m in state["messages"])
        # Grounding a recall may quote: the user's words, tool results, and the durable memory
        # (built from the conversation and safety-checked) — never the assistant's own answers.
        grounding = known_ids_text(state["messages"]) + "\n" + memory_text(state)
        plan = policy.verify_request_type(policy.TurnPlan(**state["plan"]),
                                          str(state["messages"][-1].content), grounding)
        plan = policy.enforce_evidence(plan, has_evidence)
        loadout = policy.select_tools(plan, read_tools) + write_gate.released_writes(approval=None)
        return {"plan": plan.model_dump(), "loadout": loadout, "rearmed": False, "recite": False,
                "scope": policy.SCOPES[plan.current_intent], "handoff": None, "checklist": None}

    def after_scope(state: AgentState) -> str:
        plan = policy.TurnPlan(**state["plan"])
        released = set(state["loadout"]) & write_gate.WRITE_TOOLS
        return "handoff" if plan.action_requested and not released else "answer"

    # --- handoff: Maya proposes, never files --------------------------------------
    async def handoff(state: AgentState, config) -> dict:
        context = (f"The person asking is employee {state['caller_id']} ('I', 'me', 'my' = {state['caller_id']}).\n"
                   f"Session memory:\n{memory_text(state) or '(none)'}\n\n"
                   f"Recent conversation:\n{policy.render_transcript(window(state['messages'], keep=4))}")
        try:
            proposal = await proposer.ainvoke([
                SystemMessage("Extract the access request the user just asked to file: who it is FOR, "
                              "which system, and a one-sentence business justification from the conversation."),
                HumanMessage(context)])
        except Exception:
            proposal = None
        if proposal is not None and policy.unverified_employee_id(
                {"employee_id": proposal.subject_employee_id}, state["caller_id"],
                known_ids_text(state["messages"]) + memory_text(state)):
            proposal = None                           # a guessed subject id never reaches a request
        if proposal is None:
            return {"handoff": None, "messages": [AIMessage(
                "I could not establish who needs which access, so nothing has been prepared or "
                "filed. Please name the employee (or their id) and the system.")]}
        intent = contracts.AccessRequestIntent(
            **proposal.model_dump(),
            requested_by=state["caller_id"],
            source_thread_id=config["configurable"]["thread_id"],
            request_id=config["configurable"].get("request_id", "unknown"))
        last = state["messages"][-1]
        diagnosis = (f"{last.content}\n\n" if isinstance(last, AIMessage) and not last.tool_calls
                     and isinstance(last.content, str) and last.content.strip() else "")
        messages = ([RemoveMessage(id=last.id)] if diagnosis else []) + [
            AIMessage(diagnosis + contracts.handoff_answer(intent))]
        return {"handoff": intent.model_dump(), "messages": messages}

    # --- answer / tools / rearm ---------------------------------------------------
    async def call_model(state: AgentState) -> dict:
        plan = policy.TurnPlan(**state["plan"])
        system = (policy.ANSWER_PROMPT.format(caller_id=state["caller_id"], caller_group=state["caller_group"],
                                              today=config.TODAY)
                  + policy.render_plan(plan, memory_text(state))
                  + (policy.CITE_REMINDER if state.get("recite") else ""))
        # A lookup turn gathers evidence before it may answer: until a tool has run this turn,
        # the model is bound so that it must call one.
        used_tool = any(isinstance(m, ToolMessage) for m in current_turn(state["messages"]))
        force = plan.requires_tools and not used_tool
        response = await model_for(state["loadout"], force).ainvoke(
            [SystemMessage(system), *window(state["messages"])])
        return {"messages": [response]}

    lookup = approval.mcp_caller(by_name)
    named: dict[str, list] = {}

    async def someone_else(message: str, caller_id: str) -> str | None:
        """A person other than the caller, named in this message and found in the records."""
        for name in policy.name_candidates(message):
            if name not in named:
                named[name] = (await lookup("get_employee", {"query": name}) or []) if "get_employee" in by_name else []
            rows = named[name] if isinstance(named[name], list) else []
            if rows and all(r.get("employee_id") != caller_id for r in rows):
                return name
        return None

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
            unknown = policy.unverified_employee_id(args, state["caller_id"], known_ids_text(state["messages"]))
            if not unknown and args.get("employee_id") == state["caller_id"]:
                other = await someone_else(str(current_turn(state["messages"])[0].content), state["caller_id"])
                if other:      # "Rachel Stein pinged me about HER ticket" answered with the caller's id (#28)
                    results.append(ToolMessage(
                        f"This message is about {other}, not about the caller ({state['caller_id']}). "
                        f"Look {other} up with get_employee and use their employee id.",
                        tool_call_id=call["id"], name=call["name"], status="error"))
                    continue
            if unknown:
                results.append(ToolMessage(
                    f"Employee id {unknown!r} has not been established in this conversation. "
                    "Look the person up with get_employee first.",
                    tool_call_id=call["id"], name=call["name"], status="error"))
                continue
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
        # Safety net: an answer written without a lookup that cites something no tool ever
        # returned is invented — send it back once, with the read tools (#13).
        if not used_tool and not state.get("rearmed") and contracts.citation_report(
                str(last.content), evidence(state["messages"]))["unsupported"]:
            return "rearm"
        # Tools returned evidence but the answer cites none of it, or cites a record no tool
        # returned: rewrite once, told to cite (#17, #19).
        turn_evidence = "".join(str(m.content) for m in current_turn(state["messages"])
                                if isinstance(m, ToolMessage)).replace("[]", "").strip()
        rep = contracts.citation_report(str(last.content), evidence(state["messages"]))
        if used_tool and turn_evidence and not state.get("rearmed") and (
                not rep["has_citation"] or rep["unsupported"]):
            return "recite"
        if plan.current_intent == "onboarding_status" and used_tool:
            return "checklist"
        # "I need Webex access": diagnose first (tools), then hand the request to the approval
        # workflow. A draft / recall turn never gets here: drafting is not filing (S6/S8 t3).
        if (plan.current_intent == "access_request" and plan.request_type == "lookup" and used_tool
                and policy.ASKS_FOR_ACCESS.search(str(current_turn(state["messages"])[0].content))):
            return "handoff"      # asking FOR access (W-I-03), not about an existing request (S3 t5, #27)
        return END

    def recite(state: AgentState) -> dict:
        """Drop the uncited draft and answer again with the citation reminder; same loadout."""
        return {"rearmed": True, "recite": True, "messages": [RemoveMessage(id=state["messages"][-1].id)]}

    # --- checklist: typed, cited, validated ----------------------------------------
    async def checklist(state: AgentState) -> dict:
        ev = evidence(state["messages"])
        prompt = [SystemMessage(
            "Build the onboarding checklist for the joiner discussed, from the tool evidence ONLY. "
            "One item per required system, piece of equipment, onboarding task or policy acknowledgement. "
            "Every item cites at least one source exactly as it appears in the evidence: a document "
            "path 'documents/<collection>/<file>.md' or a record id such as OT005 or SUB001. A blocked "
            "item states why it is blocked."),
            HumanMessage(f"Session memory:\n{memory_text(state) or '(none)'}\n\nTool evidence:\n{ev[-EVIDENCE_CHARS:]}")]
        errors = ["not produced"]
        proposal = None
        for _ in range(2):                            # one bounded retry with the errors fed back
            try:
                proposal = await checklister.ainvoke(prompt)
            except Exception as exc:
                proposal, errors = None, [f"extraction failed: {exc}"]
                continue
            if proposal is None:                      # the model returned nothing parseable
                errors = ["extraction returned nothing"]
                continue
            errors = contracts.checklist_errors(proposal, ev)
            if not errors:
                break
            prompt = prompt + [HumanMessage("Fix these problems and return the checklist again:\n- "
                                            + "\n- ".join(errors))]
        if proposal is None:
            return {"checklist": None}
        result = contracts.OnboardingChecklist(
            **proposal.model_dump(), status="completed" if not errors else "needs_human",
            validation_errors=errors)
        return {"checklist": result.model_dump()}

    graph = StateGraph(AgentState)
    for name, fn in [("distil", distil), ("classify", classify), ("scope", scope),
                     ("handoff", handoff), ("answer", call_model), ("tools", run_tools),
                     ("rearm", rearm), ("recite", recite), ("checklist", checklist)]:
        graph.add_node(name, fn)
    graph.add_conditional_edges(START, should_distil, {"distil": "distil", "classify": "classify"})
    graph.add_edge("distil", "classify")
    graph.add_edge("classify", "scope")
    graph.add_conditional_edges("scope", after_scope, {"handoff": "handoff", "answer": "answer"})
    graph.add_edge("handoff", END)
    graph.add_conditional_edges("answer", route,
                                {"tools": "tools", "rearm": "rearm", "recite": "recite",
                                 "checklist": "checklist", "handoff": "handoff", END: END})
    graph.add_edge("tools", "answer")
    graph.add_edge("rearm", "answer")
    graph.add_edge("recite", "answer")
    graph.add_edge("checklist", END)
    # Lesson 11: bind the Langfuse callback to the compiled graph — every node, Bedrock
    # call and MCP tool call becomes a span, for every caller. No keys -> a no-op.
    return graph.compile(checkpointer=checkpointer).with_config({"callbacks": [CallbackHandler()]})
