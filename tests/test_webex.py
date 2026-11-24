"""Milestone 4 checks that need no AWS: the seat gap, idempotent writes, the approval
record as the only key to the write, and the human channel's own authorization."""
import sys
from pathlib import Path

import pytest

from novaops import db
from novaops.agent import policy, write_gate

COUNTED = ("access_requests", "approvals", "tickets")


def counts() -> dict:
    return {t: db._rows(f"SELECT count(*) AS n FROM {t}")[0]["n"] for t in COUNTED}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db.config, "DB_PATH", tmp_path / "novaops.db")
    db.reseed()


# --- the seat gap (W-I-02) ------------------------------------------------------------

def test_team_view_says_seat_assignments_are_not_recorded():
    out = db.team_system_access("E018", "Webex")
    assert out["seat_assignments_recorded"] is False
    assert out["subscription"]["active_seats"] == 42 and out["subscription"]["seat_limit"] == 40
    team = {m["employee_id"]: m for m in out["team"]}
    assert team["E010"]["access_requests"][0]["status"] == "blocked"        # Rachel: AR001 blocked
    assert team["E003"]["entitled_by_role"] is False                         # Noam: not entitled
    assert all(m["seat_assignment"] == "not recorded" for m in team.values())


def test_a_non_manager_has_no_team():
    assert db.team_system_access("E010", "Webex")["team"] == []


# --- approvals and the write ----------------------------------------------------------

def test_existing_open_approval_is_reused():
    before = counts()
    ap = db.request_approval("access_request", "AR001", "E006", "IT Manager must approve.")
    assert ap["approval_id"] == "AP001" and ap["reused"] and counts() == before


def test_write_is_refused_without_a_recorded_approval():
    with pytest.raises(PermissionError):
        db.create_access_request("E010", "Webex", "x", "AP001")              # AP001 is only 'needed'
    with pytest.raises(PermissionError):
        db.create_access_request("E010", "Webex", "x", "AP999")


def test_only_the_named_approver_can_decide():
    with pytest.raises(PermissionError):
        db.record_approval("AP001", "E010", approved=True)                   # Rachel cannot approve herself


def test_approved_replay_reuses_ar001_and_creates_no_row():
    db.record_approval("AP001", "E006", approved=True, reason="ok")
    before = counts()
    first = db.create_access_request("E010", "Webex", "Customer calls.", "AP001")
    second = db.create_access_request("E010", "Webex", "Customer calls.", "AP001")
    assert first["request_id"] == second["request_id"] == "AR001"
    assert first["reused"] and second["reused"] and counts() == before


def test_new_request_is_written_once():
    ap = db.request_approval("access_request_intent", "req-1", "E006", "Maya needs Webex.")
    db.record_approval(ap["approval_id"], "E006", approved=True)
    first = db.create_access_request("E001", "Webex", "CSM calls.", ap["approval_id"])
    again = db.create_access_request("E001", "Webex", "CSM calls.", ap["approval_id"])
    assert not first["reused"] and again["reused"] and first["request_id"] == again["request_id"]
    assert db._rows("SELECT count(*) AS n FROM access_requests WHERE employee_id='E001' AND system_id='S001'")[0]["n"] == 1


def test_a_closed_decision_cannot_be_flipped():
    db.record_approval("AP001", "E006", approved=False, reason="no seats")
    with pytest.raises(ValueError):
        db.record_approval("AP001", "E006", approved=True)


# --- what the model can see ------------------------------------------------------------

def test_writes_and_app_tools_never_reach_a_model():
    served = set().union(*[set(v or []) for v in policy.LOADOUTS.values()])
    assert not served & (write_gate.WRITE_TOOLS | policy.APP_TOOLS)
    assert write_gate.released_writes(None) == []
    assert write_gate.released_writes({"status": "needed"}) == []
    assert write_gate.released_writes({"status": "approved"}) == ["create_access_request"]


def test_server_serves_the_new_tools():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
    import server
    names = {t.name for t in server.mcp._tool_manager.list_tools()}
    assert {"list_access_requests", "check_team_system_access", "create_access_request",
            "request_approval", "get_approval"} <= names


# --- the approval workflow: pause, die, resume, replay (no model, no AWS) --------------

import asyncio  # noqa: E402

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402

from novaops.agent import approval, contracts  # noqa: E402

FAKE_TOOLS = {
    "get_employee": lambda a: db.get_employee(a["query"]),
    "check_software_subscription": lambda a: db.check_software_subscription(a["software"]),
    "list_access_requests": lambda a: db.list_access_requests(a["employee_id"]),
    "list_employee_tickets": lambda a: db.list_employee_tickets(a["employee_id"]),
    "request_approval": lambda a: db.request_approval(**a),
    "get_approval": lambda a: db.get_approval(a["approval_id"]),
    "create_access_request": lambda a: db.create_access_request(**a),
}
CALLS: list[str] = []


async def fake_call(name, args):
    CALLS.append(name)
    return FAKE_TOOLS[name](args)


RACHEL = {"subject_employee_id": "E010", "subject_name": "Rachel Stein", "system": "Webex",
          "justification": "Customer onboarding calls require Webex.", "requested_by": "E010",
          "source_thread_id": "W-I-03", "request_id": "req-test", "status": "pending_approval"}


async def run_until_pause(ckpt, intent=RACHEL):
    async with AsyncSqliteSaver.from_conn_string(str(ckpt)) as saver:   # one "process"
        app = approval.build_approval_graph(fake_call, saver)
        cfg = {"configurable": {"thread_id": approval.thread_for(intent["subject_employee_id"], intent["system"])}}
        out = await app.ainvoke({"intent": intent, "trace_id": None}, cfg)
        return out, (await app.aget_state(cfg))


async def resume(ckpt, intent=RACHEL):
    async with AsyncSqliteSaver.from_conn_string(str(ckpt)) as saver:   # a NEW "process"
        app = approval.build_approval_graph(fake_call, saver)
        cfg = {"configurable": {"thread_id": approval.thread_for(intent["subject_employee_id"], intent["system"])}}
        from langgraph.types import Command
        await app.ainvoke(Command(resume={"note": "the payload is ignored"}), cfg)
        return await app.aget_state(cfg)


def test_rachel_pauses_pending_reusing_t001_ar001_ap001(tmp_path):
    before = counts()
    out, state = asyncio.run(run_until_pause(tmp_path / "ck.db"))
    assert "__interrupt__" in out and state.next == ("wait",)
    d = approval.build_decision(state.values)
    assert (d.decision, d.status, d.approval_id, d.access_request_id) == ("pending_approval", "pending", "AP001", "AR001")
    assert any("42 active seats against a 40-seat limit" in f for f in d.observed_facts)
    assert any("T001" in a for a in d.actions_taken) and counts() == before
    assert "create_access_request" not in CALLS
    assert not contracts.claims_granted(contracts.decision_answer(d))


def test_replaying_the_request_creates_nothing(tmp_path):
    asyncio.run(run_until_pause(tmp_path / "ck.db"))
    before = counts()
    asyncio.run(run_until_pause(tmp_path / "ck.db"))
    assert counts() == before


def test_resume_without_a_recorded_decision_stays_paused(tmp_path):
    asyncio.run(run_until_pause(tmp_path / "ck.db"))
    state = asyncio.run(resume(tmp_path / "ck.db"))      # someone says "approved" — no record
    assert state.next == ("wait",)
    assert approval.build_decision(state.values).status == "pending"


def test_survives_process_death_and_releases_only_on_the_record(tmp_path):
    asyncio.run(run_until_pause(tmp_path / "ck.db"))     # process 1 pauses, then "dies"
    db.record_approval("AP001", "E006", approved=True, reason="IT approves the path")
    before = counts()
    state = asyncio.run(resume(tmp_path / "ck.db"))      # process 2 resumes from SQLite
    d = approval.build_decision(state.values)
    assert state.next == () and d.decision == "request_on_file"
    assert d.status == "blocked" and "42 of 40" in d.blocking_reason        # approved, still no seat
    assert d.access_request_id == "AR001" and counts() == before             # reused, not duplicated
    assert any("reused AR001" in a for a in d.actions_taken)
    assert any("AP001 (access_request) by E006 is approved" in f for f in d.observed_facts)
    assert not contracts.claims_granted(contracts.decision_answer(d))


def test_rejection_is_reported_and_nothing_is_filed(tmp_path):
    asyncio.run(run_until_pause(tmp_path / "ck.db"))
    db.record_approval("AP001", "E006", approved=False, reason="wait for renewal")
    CALLS.clear()
    d = approval.build_decision(asyncio.run(resume(tmp_path / "ck.db")).values)
    assert (d.decision, d.status) == ("rejected", "blocked") and "create_access_request" not in CALLS


def test_not_entitled_files_no_approval(tmp_path):
    noam = {**RACHEL, "subject_employee_id": "E003", "subject_name": "Noam Sharon"}
    before = counts()
    out, state = asyncio.run(run_until_pause(tmp_path / "ck.db", noam))
    d = approval.build_decision(state.values)
    assert "__interrupt__" not in out and (d.decision, d.status) == ("not_eligible", "needs_human")
    assert counts() == before


def test_approver_cli_finds_the_paused_thread_from_the_record():
    from novaops import approve
    assert approve.subject_of(db.get_approval("AP001")) == ("E010", "Webex")          # via AR001
    ap = db.request_approval("access_request_intent", "E001:Webex", "E006", "x")
    assert approval.thread_for(*approve.subject_of(ap)) == "approval-E001-webex"


def test_a_typo_in_a_name_still_finds_the_person():
    rows = db.get_employee("rrachel stein")                     # S8 turn 2
    assert [r["employee_id"] for r in rows] == ["E010"] and "matched_by" in rows[0]
    assert db.get_employee("Nobody Atall") == []


def test_a_seat_question_read_as_a_people_question_still_sees_the_gap_tool():
    assert "check_team_system_access" in policy.LOADOUTS["employee_lookup"]          # W-I-02 (#22)
    assert "check_team_system_access" in policy.LOADOUTS["subscription_review"]


# --- S3/S4: a decision is not a write; a status question is not a request (#27) ----------

def _plan(kind, action=False):
    return policy.TurnPlan(current_intent="access_request", request_type=kind, action_requested=action)


def test_closing_a_topic_never_reaches_the_write_path():
    p = policy.verify_request_type(_plan("action", True),
                                   "Good — that one's covered, the seat expansion is already with Amir. Treat it as resolved.", "")
    assert p.request_type == "acknowledge" and p.action_requested is False and not p.requires_tools


def test_real_filing_requests_stay_actions():
    for msg in ("Go ahead and file the Webex access request for her now.",
                "OK, I'm saying so: file the Webex access request for Rachel Stein."):
        assert policy.verify_request_type(_plan("action", True), msg, "").action_requested is True


def test_ground_rules_need_no_lookup_even_on_turn_one():
    p = policy.verify_request_type(_plan("acknowledge"), "Ground rules for this session: anything above 7,500 needs Finance.", "")
    assert policy.enforce_evidence(p, has_evidence=False).request_type == "acknowledge"
    q = policy.verify_request_type(_plan("acknowledge"), "Which of those needs Finance?", "")
    assert q.request_type == "lookup"


def test_only_asking_for_access_starts_the_approval_workflow():
    assert policy.ASKS_FOR_ACCESS.search("I joined Customer Success and need Webex access.")
    assert not policy.ASKS_FOR_ACCESS.search("Does he have a GitHub request already waiting on someone?")


def test_names_in_a_message_are_candidates_to_check():
    # M-S-01 t4: "Rachel Stein pinged me about her Webex login ticket" was answered with the
    # caller's own id (E004). The graph now checks capitalised names against the records (#28).
    assert "Rachel Stein" in policy.name_candidates("Quick tangent — Rachel Stein pinged me about her ticket.")
    assert policy.name_candidates("what is the status of my ticket?") == []


def test_a_descriptive_subscription_query_still_finds_the_system():
    # M-S-01 t8 (final run B): the model asked for "Webex standard user license" and got nothing (#29)
    rows = db.check_software_subscription("Webex standard user license")
    assert rows and rows[0]["subscription_id"] == "SUB001" and rows[0]["active_seats"] == 42
