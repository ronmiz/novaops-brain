"""Run EVALUATION-INPUTS.yaml through the agent the way spec section 13 says, and index the traces.

    python evals/run_submission.py --only M-I-01 --only M-I-02 --only M-I-03   # a rehearsal
    python evals/run_submission.py --write-submission                          # THE run: 27 traces

Rules from spec 13, enforced here rather than remembered:
  - reseed the database before each independent case or session (cases touch the same rows);
  - a session is ONE thread on ONE database, turns in order; an input is a NEW thread;
  - the clock is pinned (config.TODAY = 2026-07-01, read by the agent);
  - one trace per turn (run.ask opens one root span per turn).

Required workflows only (maya, webex). Results go to evals/results/submission-<stamp>.json;
`--write-submission` copies the template next to the repo root if needed and fills its trace-id
column. Register the LLM judges first (evals/register_judges.py) — they only judge new turns.
Needs the MCP server running.
"""
import argparse
import asyncio
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from novaops import config, db  # noqa: E402
from novaops.agent.run import ask, langfuse  # noqa: E402
import golden_replay  # noqa: E402  (same directory: the same checks the golden replay uses)

INPUTS = config.DATASET_DIR.parent / "EVALUATION-INPUTS.yaml"
TEMPLATE = config.DATASET_DIR.parent / "SUBMISSION.md"
SUBMISSION = ROOT / "SUBMISSION.md"
REQUIRED = ("maya", "webex")
OPTIONAL = ("vendor",)          # renewal joins when it is built
EXPECTED = json.loads((Path(__file__).parent / "expected_inputs.json").read_text(encoding="utf-8"))


def expectation(item_id: str, turn: int | None) -> tuple[str, dict]:
    """(session id for the carry checks, the turn's expectations) — ours for the one-shot
    inputs, the golden session's for the three sessions (evals/expected_inputs.json)."""
    if item_id in EXPECTED["inputs"]:
        return item_id, {"n": 0, **EXPECTED["inputs"][item_id]}
    golden_id = EXPECTED["sessions"][item_id]
    session = next(s for s in json.loads(golden_replay.GOLDEN.read_text(encoding="utf-8"))["sessions"]
                   if s["id"].startswith(golden_id))
    return session["id"], next(t for t in session["turns"] if t["n"] == turn)


def items(only: list[str] | None, optional: bool = False) -> list[dict]:
    """Every required input and session, in file order, as (id, caller, [(turn, message)])."""
    out = []
    for wf in yaml.safe_load(INPUTS.read_text(encoding="utf-8"))["workflows"]:
        if wf["id"] not in REQUIRED + (OPTIONAL if optional else ()):
            continue
        if wf["id"] == "vendor":       # a document, no caller, no conversation (spec 10)
            out += [{"id": c["id"], "vendor": c} for c in wf["inputs"]]
            continue
        for case in wf.get("inputs") or []:
            out.append({"id": case["id"], "caller": case["caller"], "turns": [(None, case["message"])]})
        for case in wf.get("sessions") or []:
            out.append({"id": case["id"], "caller": case["caller"],
                        "turns": [(t["n"], t["message"]) for t in case["turns"]]})
    return [i for i in out if not only or i["id"] in only]


async def run_item(item: dict) -> list[dict]:
    db.reseed()                                          # independent case or session: fresh rows
    thread = f"{item['id']}-{uuid.uuid4().hex[:6]}"      # one thread for every turn of this item
    rows = []
    for turn, message in item["turns"]:
        r = await ask(message, item["caller"]["employee_id"], item["caller"]["group"], thread)
        session_id, expected = expectation(item["id"], turn)
        checks = golden_replay.check_turn(session_id, expected, r)
        if expected.get("status"):
            checks["status"] = (r.get("status") == expected["status"], r.get("status"))
        failed = {k: v[1] for k, v in checks.items() if not v[0]}
        if r.get("trace_id"):
            langfuse.create_score(trace_id=r["trace_id"], name="expected_pass", value=0.0 if failed else 1.0,
                                  data_type="NUMERIC", comment=json.dumps(failed, ensure_ascii=False)[:500] or None)
        rows.append({"item": item["id"], "turn": turn, "thread_id": thread, "trace_id": r.get("trace_id"),
                     "pass": not failed, "failed": failed,
                     "status": r.get("status"), "intent": r.get("intent"), "tools_used": r.get("tools_used"),
                     "access_decision": r.get("access_decision"), "answer": r.get("answer")})
        print(f"  {item['id']:<7} t{turn or '-':<3} {'PASS' if not failed else 'FAIL'}  {r.get('status'):<11} "
              f"{r.get('intent') or '-':<20} trace={r.get('trace_id')}")
        for k, v in failed.items():
            print(f"           x {k}: {v}")
    return rows


def fill_submission(rows: list[dict]) -> None:
    text = (SUBMISSION if SUBMISSION.exists() else TEMPLATE).read_text(encoding="utf-8")
    for r in rows:
        turn = "—" if r["turn"] is None else str(r["turn"])
        row = re.compile(rf"^\| `{re.escape(r['item'])}` \| {re.escape(turn)} \|[^\n]*$", re.M)
        text, n = row.subn(f"| `{r['item']}` | {turn} | `{r['trace_id']}` |", text)
        if n != 1:
            print(f"  ! no unique row for {r['item']} turn {turn} in SUBMISSION.md")
    SUBMISSION.write_text(text, encoding="utf-8")


def run_vendor(item: dict) -> list[dict]:
    """Workflow 3 never touches the agent: one traced call of novaops.vendor.extract."""
    from novaops import vendor
    case = item["vendor"]
    with langfuse.start_as_current_observation(as_type="chain", name="vendor-extraction",
                                               input={"source": case["source_name"]}) as span:
        try:
            result, status = vendor.extract(case["document"], case["source_name"]), "completed"
        except Exception as exc:                                   # invalid output = truthful failure
            result, status = {"error": str(exc)}, "failed"
        span.update(output=result, metadata={"status": status, "source_id": case["source_name"],
                                             "missing_required_fields": result.get("missing_required_fields")})
        trace_id = langfuse.get_current_trace_id()
    want = EXPECTED["inputs"][item["id"]]["missing_required_fields"]
    got = result.get("missing_required_fields")
    failed = {} if got == want else {"missing_required_fields": {"expected": want, "got": got}}
    langfuse.create_score(trace_id=trace_id, name="expected_pass", value=0.0 if failed else 1.0,
                          data_type="NUMERIC", comment=json.dumps(failed)[:500] or None)
    print(f"  {item['id']:<7} t-   {'PASS' if not failed else 'FAIL'}  {status:<11} vendor               "
          f"missing={got} trace={trace_id}")
    return [{"item": item["id"], "turn": None, "trace_id": trace_id, "status": status, "pass": not failed,
             "failed": failed, "answer": json.dumps(result, ensure_ascii=False)}]


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only", action="append", help="item id, e.g. M-I-01 (repeatable)")
    p.add_argument("--write-submission", action="store_true", help="fill the trace ids into SUBMISSION.md")
    p.add_argument("--optional", action="store_true", help="also run the optional workflows built so far")
    args = p.parse_args()
    todo = items(args.only, args.optional)
    print(f"{len(todo)} items, {sum(len(i.get('turns', [None])) for i in todo)} traces, clock {config.TODAY}\n")
    rows = []
    for item in todo:
        rows += run_vendor(item) if "vendor" in item else await run_item(item)
    langfuse.flush()
    tag = "all" if not args.only else "-".join(args.only)
    out = ROOT / "evals" / "results" / f"submission-{tag}-{datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(rows)} traces · {sum(r['pass'] for r in rows)}/{len(rows)} meet our expectations · "
          f"statuses {sorted({r['status'] for r in rows})} · saved {out.relative_to(ROOT)}")
    if args.write_submission:
        fill_submission(rows)
        print(f"trace ids written to {SUBMISSION.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
