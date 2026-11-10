"""The ONE entry point into the agent. Tests, the CLI, the eval runner and (later) the UI
all call `ask()`. There is no second path into the workflow (spec 6.6).

Tracing (Lesson 11): graph.py binds the Langfuse callback, so every node, model call and
tool call is a span. THIS file adds what only the caller knows: who is asking, which
conversation this is, and how the turn ended. Every turn is one trace:
    root span "novaops-turn" (input = message, output = answer) — the span the LLM judges read
    metadata  request_id, caller_id, caller_group, scope, intent, loadout, tool_sequence, status
    session   = thread_id (a multi-turn conversation reads as one session in Langfuse)
    user      = caller_id

    python server/server.py                                              # terminal 1
    python -m novaops.agent.run E010 "Can I use my personal laptop for work?"
    python -m novaops.agent.run E010 "What is the status of my Webex login ticket?"
    python -m novaops.agent.run E004 "Pull up Maya Cohen's record" --group "HR Group" --thread s2
"""
import argparse
import asyncio
import uuid

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langfuse import get_client, propagate_attributes
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .. import config
from . import approval
from .contracts import attach_sources, citation_report, decision_answer, sources_in
from .graph import build_graph, current_turn, evidence
from .memory import render_memory

CHECKPOINT_DB = config.DB_PATH.parent / "checkpoints.db"
STATUSES = ("completed", "blocked", "pending", "needs_human", "failed")
RECURSION_LIMIT = 25
# One fixed name for the span a judge reads (and the trace name). Caller and thread are the
# trace's user and session, so nothing is lost; the evaluation rules filter on this name.
TURN_SPAN = "novaops-turn"

langfuse = get_client()   # reads LANGFUSE_PUBLIC_KEY / _SECRET_KEY / _BASE_URL; no keys -> no-op


async def _run_turn(message: str, caller_id: str, caller_group: str, thread_id: str,
                    request_id: str) -> dict:
    tools = await load_tools()
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    decision, workflow_tools = None, []
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as saver:
        graph = build_graph(tools, checkpointer=saver)
        state = await graph.ainvoke(
            {"messages": [HumanMessage(message)], "caller_id": caller_id, "caller_group": caller_group},
            config={"configurable": {"thread_id": thread_id, "request_id": request_id},
                    "recursion_limit": RECURSION_LIMIT, "run_name": "agent-turn"})
        if state.get("handoff"):
            # Webex consumes the handoff: file (or reuse) the approval request and pause. The
            # pause lives on its own thread in the same SQLite file, so the conversation goes on
            # and the approval survives a restart. Same trace: we are inside the turn's root span.
            decision = await approval.start(approval_app(tools, saver, workflow_tools), state["handoff"],
                                            langfuse.get_current_trace_id())
    turn = current_turn(state["messages"])
    answer = turn[-1].content if isinstance(turn[-1].content, str) else str(turn[-1].content)
    turn_evidence = evidence(turn)
    answer = attach_sources(answer, turn_evidence)
    # Checked against tool evidence: what the MODEL wrote. The AccessDecision text below is
    # rendered by code from the records the approval workflow read, citations included.
    citations = citation_report(answer, evidence(state["messages"]))
    if decision:
        answer = f"{answer}\n\n{decision_answer(decision)}"
    return {
        # status = where the workflow got to. A handoff waits for a human approval.
        "status": decision.status if decision else "pending" if state.get("handoff") else "completed",
        "answer": answer,
        "intent": state["plan"]["current_intent"],
        "request_type": state["plan"].get("request_type"),      # after code verification
        "answer_quote": state["plan"].get("answer_quote"),
        "scope": state["scope"],
        "loadout": state["loadout"],
        # the model's tool calls, then the approval workflow's (application code, same turn)
        "tools_used": [m.name for m in turn if isinstance(m, ToolMessage)] + workflow_tools,
        "sources_seen": sorted(sources_in(turn_evidence)),
        "evidence_returned": bool(turn_evidence.replace("[]", "").strip()),
        "citations": citations,
        "constraints": state["plan"].get("relevant_constraints", []),
        "memory": state.get("memory") or {},
        "handoff": state.get("handoff"),
        "access_decision": decision.model_dump() if decision else None,
        "trajectory": trajectory(turn, state, decision),
        "checklist": state.get("checklist"),
    }


CALL_CHARS, EARLIER_CHARS = 1500, 3000


def trajectory(turn: list, state: dict, decision) -> dict:
    """The evidence an LLM judge needs, copied onto the turn's root span (Lesson 11, ex. 4):
    a Langfuse evaluation rule reads ONE observation, and the tool observations sit beside
    the root span, not inside it. `calls` = what tools returned THIS turn; `state` = what
    earlier turns established (memory, user rules, earlier tool results). Truncated copies."""
    calls = [{"tool": m.name, "result": str(m.content)[:CALL_CHARS]} for m in turn if isinstance(m, ToolMessage)]
    if decision:
        calls.append({"tool": "approval_workflow (application code)",
                      "result": {"observed": decision.observed_facts, "actions": decision.actions_taken,
                                 "status": decision.status}})
    earlier = evidence(state["messages"][:len(state["messages"]) - len(turn)])
    return {"calls": calls,
            "state": {"user_rules": state["plan"].get("relevant_constraints", []),
                      "memory": render_memory(state.get("memory") or {}),
                      "earlier_tool_results": earlier[-EARLIER_CHARS:]}}


async def load_tools() -> list:
    return await MultiServerMCPClient(
        {"novaops": {"url": config.MCP_URL, "transport": "streamable_http"}}).get_tools()


def approval_app(tools: list, saver, log: list | None = None):
    return approval.build_approval_graph(approval.mcp_caller({t.name: t for t in tools}, log), saver,
                                         callbacks=[CallbackHandler()])


async def ask(message: str, caller_id: str, caller_group: str, thread_id: str | None = None) -> dict:
    """Run one turn. Caller identity and group are application inputs. Returns a typed
    result whose `status` is one of STATUSES, plus the Langfuse trace id."""
    thread_id = thread_id or f"t-{uuid.uuid4().hex[:8]}"
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    with propagate_attributes(session_id=thread_id, user_id=caller_id, tags=["novaops-brain"],
                              metadata={"request_id": request_id, "caller_group": caller_group}):
        with langfuse.start_as_current_observation(
                as_type="agent", name=TURN_SPAN, input=message) as root:
            try:
                result = await _run_turn(message, caller_id, caller_group, thread_id, request_id)
            except Exception as exc:          # a failure is reported truthfully, never hidden
                result = {"status": "failed", "answer": f"The request failed: {exc}"}
            result.update(thread_id=thread_id, request_id=request_id,
                          trace_id=langfuse.get_current_trace_id())
            root.update(output=result["answer"], metadata={
                "request_id": request_id, "caller_id": caller_id, "caller_group": caller_group,
                "scope": result.get("scope"), "intent": result.get("intent"),
                "loadout": result.get("loadout"), "tool_sequence": result.get("tools_used"),
                "sources_seen": result.get("sources_seen"), "citations": result.get("citations"),
                "handoff": result.get("handoff"), "checklist": result.get("checklist"),
                "access_decision": result.get("access_decision"),
                "trajectory": result.get("trajectory"),
                "status": result["status"],
            })
            try:
                result["trace_url"] = langfuse.get_trace_url()
            except Exception:
                result["trace_url"] = None
    langfuse.flush()   # a short-lived process must flush, or the trace never leaves
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("caller_id")
    p.add_argument("message")
    p.add_argument("--group", default="Regular Employee")
    p.add_argument("--thread")
    args = p.parse_args()
    r = asyncio.run(ask(args.message, args.caller_id, args.group, args.thread))
    for key in ("status", "thread_id", "intent", "scope", "loadout", "tools_used", "sources_seen",
                "citations", "handoff", "access_decision", "trace_id", "trace_url"):
        print(f"{key:<11}{r.get(key)}")
    print(f"\n{r['answer']}\n")
    if r.get("checklist"):
        import json
        print("checklist:", json.dumps(r["checklist"], indent=2))


if __name__ == "__main__":
    main()
