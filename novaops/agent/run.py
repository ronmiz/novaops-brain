"""The ONE entry point into the agent. Tests, the CLI, the eval runner and (later) the UI
all call `ask()`. There is no second path into the workflow (spec 6.6).

Tracing (Lesson 11): graph.py binds the Langfuse callback, so every node, model call and
tool call is a span. THIS file adds what only the caller knows: who is asking, which
conversation this is, and how the turn ended. Every turn is one trace:
    root span "<caller> · <thread>" (input = message, output = answer)
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
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .. import config
from .contracts import citation_report, sources_in
from .graph import build_graph, current_turn, evidence

CHECKPOINT_DB = config.DB_PATH.parent / "checkpoints.db"
STATUSES = ("completed", "blocked", "pending", "needs_human", "failed")
RECURSION_LIMIT = 25

langfuse = get_client()   # reads LANGFUSE_PUBLIC_KEY / _SECRET_KEY / _BASE_URL; no keys -> no-op


async def _run_turn(message: str, caller_id: str, caller_group: str, thread_id: str,
                    request_id: str) -> dict:
    tools = await MultiServerMCPClient(
        {"novaops": {"url": config.MCP_URL, "transport": "streamable_http"}}).get_tools()
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as saver:
        graph = build_graph(tools, checkpointer=saver)
        state = await graph.ainvoke(
            {"messages": [HumanMessage(message)], "caller_id": caller_id, "caller_group": caller_group},
            config={"configurable": {"thread_id": thread_id, "request_id": request_id},
                    "recursion_limit": RECURSION_LIMIT, "run_name": "agent-turn"})
    turn = current_turn(state["messages"])
    answer = turn[-1].content if isinstance(turn[-1].content, str) else str(turn[-1].content)
    turn_evidence = evidence(turn)
    return {
        # status = where the workflow got to. A handoff waits for a human approval.
        "status": "pending" if state.get("handoff") else "completed",
        "answer": answer,
        "intent": state["plan"]["current_intent"],
        "scope": state["scope"],
        "loadout": state["loadout"],
        "tools_used": [m.name for m in turn if isinstance(m, ToolMessage)],
        "sources_seen": sorted(sources_in(turn_evidence)),
        "evidence_returned": bool(turn_evidence.replace("[]", "").strip()),
        "citations": citation_report(answer, evidence(state["messages"])),
        "constraints": state["plan"].get("relevant_constraints", []),
        "memory": state.get("memory") or {},
        "handoff": state.get("handoff"),
        "checklist": state.get("checklist"),
    }


async def ask(message: str, caller_id: str, caller_group: str, thread_id: str | None = None) -> dict:
    """Run one turn. Caller identity and group are application inputs. Returns a typed
    result whose `status` is one of STATUSES, plus the Langfuse trace id."""
    thread_id = thread_id or f"t-{uuid.uuid4().hex[:8]}"
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    with propagate_attributes(session_id=thread_id, user_id=caller_id, tags=["novaops-brain"],
                              metadata={"request_id": request_id, "caller_group": caller_group}):
        with langfuse.start_as_current_observation(
                as_type="agent", name=f"{caller_id} · {thread_id}", input=message) as root:
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
                "citations", "handoff", "trace_id", "trace_url"):
        print(f"{key:<11}{r.get(key)}")
    print(f"\n{r['answer']}\n")
    if r.get("checklist"):
        import json
        print("checklist:", json.dumps(r["checklist"], indent=2))


if __name__ == "__main__":
    main()
