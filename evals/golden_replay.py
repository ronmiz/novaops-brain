"""Replay golden sessions through the real agent and score the BINDING expectations.

GOLDEN-DATASETS.json `_readme`: required_facts, forbidden_facts, forbidden_tools,
forbidden_sources, expected_sources and should_use_tools bind regardless of architecture;
expected_tools / sequence are illustrative and are NOT scored here.

Plus the checks the datasets deliberately do not ship (spec section 5, "write the checks
nothing ships"):
  citations     a turn that used tools cites at least one source, and every cited
                document/record actually came back from a tool (no invented citations)
  constraint    a constraint stated early is still in force on the turn that needs it
                (S2 turn 9: the Q3 SaaS freeze from turn 1)
  no_write      no write tool fired, ever (Maya never files)

Each session runs on ONE thread against a freshly reseeded database (spec section 13).
Needs the MCP server running.

    python evals/golden_replay.py                 # S1, S2, S9
    python evals/golden_replay.py --session S9
"""
import argparse
import asyncio
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novaops import config, db  # noqa: E402
from novaops.agent import write_gate  # noqa: E402
from novaops.agent.run import ask  # noqa: E402

GOLDEN = config.DATASET_DIR.parent / "GOLDEN-DATASETS.json"
GROUP_NAMES = {"UG_REGULAR": "Regular Employee", "UG_HR": "HR Group", "UG_IT": "IT Group"}
# Constraint-carry checks: (session prefix, turn) -> words one of which must appear in the
# constraints the agent carried into that turn.
CONSTRAINT_CARRY = {("S2", 9): ["freeze"]}


def matches(text: str, expectation: str) -> bool:
    """Case-insensitive; '|' separates acceptable alternatives (golden _readme)."""
    return any(alt.strip().lower() in text.lower() for alt in expectation.split("|"))


def check_turn(session_id: str, turn: dict, r: dict) -> dict:
    answer, tools, seen = r.get("answer", ""), r.get("tools_used", []), r.get("sources_seen", [])
    checks = {}
    if turn.get("required_facts"):
        missing = [f for f in turn["required_facts"] if not matches(answer, f)]
        checks["required_facts"] = (not missing, missing)
    if turn.get("forbidden_facts"):
        present = [f for f in turn["forbidden_facts"] if matches(answer, f)]
        checks["forbidden_facts"] = (not present, present)
    if turn.get("forbidden_tools"):
        fired = sorted(set(tools) & set(turn["forbidden_tools"]))
        checks["forbidden_tools"] = (not fired, fired)
    if turn.get("should_use_tools") is not None:
        used = bool(tools)
        checks["should_use_tools"] = (used == turn["should_use_tools"], f"used={used}")
    if turn.get("forbidden_sources"):
        leaked = [s for s in seen if any(s.endswith(f) for f in turn["forbidden_sources"])]
        checks["forbidden_sources"] = (not leaked, leaked)
    if turn.get("expected_sources"):
        hit = [s for s in seen if any(s.endswith(e) for e in turn["expected_sources"])]
        checks["expected_sources"] = (bool(hit), hit or seen)
    # --- our own checks ---
    checks["no_write"] = (not (set(tools) & write_gate.WRITE_TOOLS), "")
    c = r.get("citations", {})
    if c.get("unsupported"):                       # an invented citation always fails
        checks["citations"] = (False, {"unsupported": c["unsupported"]})
    elif tools and r.get("evidence_returned"):     # evidence came back -> the answer must cite it
        checks["citations"] = (bool(c.get("has_citation")), "no citation")
    words = CONSTRAINT_CARRY.get((session_id.split("-")[0], turn["n"]))
    if words:
        carried = " ".join(r.get("constraints", []) + r.get("memory", {}).get("active_constraints", []))
        checks["constraint"] = (any(w in carried.lower() for w in words), carried[:200])
    if r.get("status") == "failed":
        checks["status"] = (False, r.get("answer"))
    return checks


def caller_of(session: dict) -> tuple[str, str]:
    """S2/S9 carry caller_id/caller_group; the other sessions only name the caller in
    `persona` ('Rachel Stein (E010, ...)') — read the id there (as Lesson 11's runner
    does) and take the group from the employee record."""
    caller_id = session.get("caller_id") or re.search(r"\((E\d{3})", session["persona"]).group(1)
    group_id = session.get("caller_group") or db.get_employee(caller_id)[0]["user_group_id"]
    return caller_id, GROUP_NAMES.get(group_id, group_id)


async def replay(session: dict) -> list[dict]:
    db.reseed()
    thread = f"{session['id'].split('-')[0]}-{uuid.uuid4().hex[:6]}"
    caller_id, group = caller_of(session)
    rows = []
    for turn in session["turns"]:
        r = await ask(turn["user"], caller_id, group, thread)
        checks = check_turn(session["id"], turn, r)
        failed = {k: v[1] for k, v in checks.items() if not v[0]}
        rows.append({"session": session["id"], "turn": turn["n"], "kind": turn.get("kind"),
                     "pass": not failed, "failed": failed, "status": r.get("status"),
                     "intent": r.get("intent"), "tools_used": r.get("tools_used"),
                     "sources_seen": r.get("sources_seen"), "handoff": r.get("handoff"),
                     "checklist": r.get("checklist"), "answer": r.get("answer"),
                     "trace_id": r.get("trace_id")})
        mark = "PASS" if not failed else "FAIL"
        print(f"  {session['id'][:3]} t{turn['n']:>2} {mark}  {r.get('status'):<9} "
              f"{r.get('intent') or '-':<20} tools={','.join(r.get('tools_used') or []) or '-'}")
        for k, v in failed.items():
            print(f"           ✗ {k}: {v}")
    return rows


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--session", action="append", help="session id prefix (repeatable)")
    args = p.parse_args()
    wanted = args.session or ["S1", "S2", "S9"]
    sessions = [s for s in json.loads(GOLDEN.read_text(encoding="utf-8"))["sessions"]
                if any(s["id"].startswith(w) for w in wanted)]
    rows = []
    for s in sessions:
        caller_id, group = caller_of(s)
        print(f"\n{s['id']} ({caller_id}, {group})")
        rows += await replay(s)
    passed = sum(r["pass"] for r in rows)
    print(f"\nTOTAL {passed}/{len(rows)} turns pass all binding + own checks")
    out = Path(__file__).parent / "results" / f"golden-{'-'.join(wanted)}-{datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {out.relative_to(config.ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
