"""Milestone 5 checks that need no network: the judges read exactly the span and fields the
entry point writes."""
import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from novaops.agent import run

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))
import register_judges  # noqa: E402


def test_rules_fire_on_the_span_the_entry_point_writes():
    rule = register_judges.rule_payload("faithfulness", True, "ev-1")
    names = [f for f in rule["filter"] if f["column"] == "name"][0]["value"]
    assert names == [run.TURN_SPAN] == [register_judges.TURN_SPAN]


def test_judges_read_the_trajectory_digest():
    paths = {m["variable"]: m.get("jsonPath") for m in register_judges.MAPPING}
    assert paths["tool_results"] == "$.trajectory.calls" and paths["state"] == "$.trajectory.state"
    assert set(register_judges.JUDGES) == {"faithfulness", "citation_quality", "no_overclaim"}
    assert all("{{tool_results}}" in p and "{{answer}}" in p for p in register_judges.JUDGES.values())


def test_trajectory_separates_this_turn_from_earlier_evidence():
    earlier = [HumanMessage("hi"), AIMessage("", tool_calls=[{"name": "get_policy", "args": {}, "id": "1"}]),
               ToolMessage("OLD POLICY TEXT", tool_call_id="1", name="get_policy"), AIMessage("answer 1")]
    turn = [HumanMessage("and now?"), AIMessage("", tool_calls=[{"name": "get_employee", "args": {}, "id": "2"}]),
            ToolMessage('{"employee_id": "E010"}', tool_call_id="2", name="get_employee"), AIMessage("answer 2")]
    state = {"messages": earlier + turn, "plan": {"relevant_constraints": ["no filing"]}, "memory": {}}
    t = run.trajectory(turn, state, None)
    assert t["calls"] == [{"tool": "get_employee", "result": '{"employee_id": "E010"}'}]
    assert "OLD POLICY TEXT" in t["state"]["earlier_tool_results"] and t["state"]["user_rules"] == ["no filing"]


# --- the submission runner reads the set the way spec 13 says ---------------------------

import run_submission  # noqa: E402


def test_submission_set_is_27_turns_of_maya_and_webex():
    todo = run_submission.items(None)
    assert sum(len(i["turns"]) for i in todo) == 27
    assert {i["id"][0] for i in todo} == {"M", "W"}
    session = next(i for i in todo if i["id"] == "M-S-01")
    assert [t for t, _ in session["turns"]] == list(range(1, 13))


def test_trace_ids_land_in_their_own_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(run_submission, "SUBMISSION", tmp_path / "SUBMISSION.md")
    run_submission.fill_submission([{"item": "M-I-01", "turn": None, "trace_id": "abc"},
                                    {"item": "M-S-01", "turn": 10, "trace_id": "def"}])
    text = (tmp_path / "SUBMISSION.md").read_text(encoding="utf-8")
    assert "| `M-I-01` | — | `abc` |" in text and "| `M-S-01` | 10 | `def` |" in text
    assert "| `M-S-01` | 1 | |" in text                     # turn 1 untouched (no 1 vs 10 mix-up)
