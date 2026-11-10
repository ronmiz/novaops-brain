"""The HUMAN channel: an approver records a decision, then the paused workflow resumes.

    python -m novaops.approve AP001 --by E006 --approve --reason "IT approves the path"
    python -m novaops.approve AP001 --by E006 --reject  --reason "wait for the renewal"

This is the only place an approval is recorded, and it is application code, not the agent:
no model call, no tool a model can see. `db.record_approval` refuses anyone but the approver
named on the row. The resume then re-reads that row — a resume without a recorded decision
pauses again. It reports into the trace of the turn that paused (spec 13: a workflow that
pauses and resumes stays one trace) and works from a fresh process: the pause is in SQLite.
"""
import argparse
import asyncio

from langfuse import get_client
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from . import db
from .agent import approval
from .agent.contracts import decision_answer
from .agent.run import CHECKPOINT_DB, approval_app, load_tools

langfuse = get_client()


def subject_of(approval_row: dict) -> tuple[str, str]:
    """Which (employee, system) a recorded approval is about — the workflow's thread key."""
    ref = approval_row["request_id"]
    if ":" in ref:                                   # an approval filed from a handoff: "E001:Webex"
        employee_id, system = ref.split(":", 1)
        return employee_id, system
    row = db._rows("SELECT ar.employee_id, s.system_name FROM access_requests ar "
                   "JOIN systems s ON ar.system_id = s.system_id WHERE ar.request_id = ?", (ref,))[0]
    return row["employee_id"], row["system_name"]


async def decide(approval_id: str, approver_id: str, approved: bool, reason: str) -> dict:
    row = db.record_approval(approval_id, approver_id, approved, reason)
    thread = approval.thread_for(*subject_of(row))
    cfg = {"configurable": {"thread_id": thread}}
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as saver:
        app = approval_app(await load_tools(), saver)
        paused = await app.aget_state(cfg)
        if not paused.next:
            return {"recorded": row, "resumed": False, "note": f"no paused workflow on {thread}"}
        trace_id = paused.values.get("trace_id")
        with langfuse.start_as_current_observation(
                trace_context={"trace_id": trace_id} if trace_id else None, as_type="agent",
                name=f"approval-resume · {approval_id}", input={"approval_id": approval_id, "by": approver_id}) as span:
            await app.ainvoke(Command(resume={"approval_id": approval_id}), cfg)
            d = approval.build_decision((await app.aget_state(cfg)).values)
            span.update(output=decision_answer(d), metadata={"status": d.status, "decision": d.decision,
                                                             "approval_id": approval_id, "thread_id": thread})
    langfuse.flush()
    return {"recorded": row, "resumed": True, "access_decision": d.model_dump(), "answer": decision_answer(d)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("approval_id")
    p.add_argument("--by", required=True, help="the approver's employee id")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--reject", action="store_true")
    p.add_argument("--reason", default="")
    args = p.parse_args()
    out = asyncio.run(decide(args.approval_id, args.by, args.approve, args.reason))
    print(f"recorded: {out['recorded']['approval_id']} = {out['recorded']['status']} by {out['recorded']['approver_id']}")
    print(out.get("answer") or out["note"])


if __name__ == "__main__":
    main()
