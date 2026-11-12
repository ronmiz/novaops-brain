"""Workflow 4 (Renewal) without Bedrock. The persisted records are the oracle (spec 11)."""
import json
import subprocess
import sys

import pytest

from novaops import db, renewal

EVENTS = {json.loads(l)["event_id"]: json.loads(l) for l in
          (renewal.RENEWAL_DIR / "internal_approval_events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
# What a correct extraction proposes for each supplied reply.
PROPOSALS = {
    "webex_renewal_approved": {"decision": "approved", "contract_id": "C001", "confirmation_id": "RX-WEBEX-2026-8841",
                               "new_seat_limit": 50, "annual_cost_usd": 22000, "term_start_date": "2026-07-21",
                               "term_end_date": "2027-07-20", "conditions": []},
    "webex_renewal_conditional": {"decision": "conditional", "contract_id": "C001", "new_seat_limit": 50,
                                  "annual_cost_usd": 22000, "term_start_date": "2026-07-21", "term_end_date": "2027-07-20",
                                  "conditions": ["signed order form", "written Finance acceptance by 2026-07-10"]},
    "webex_renewal_rejected": {"decision": "rejected", "contract_id": "C001"},
    "webex_renewal_ambiguous": {"decision": "ambiguous", "new_seat_limit": 50},
    "webex_renewal_over_ceiling": {"decision": "approved", "contract_id": "C001", "confirmation_id": "RX-WEBEX-2026-8852",
                                   "new_seat_limit": 50, "annual_cost_usd": 24000, "term_start_date": "2026-07-21",
                                   "term_end_date": "2027-07-20", "conditions": []},
}


def fake_recommender(facts):
    return {"action": "expand" if facts["active_seats"] and facts["active_seats"] > facts["seat_limit"] else "renew_as_is",
            "rationale": "test", "uncertainty": "none"}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db.config, "DB_PATH", tmp_path / "novaops.db")
    db.reseed()


def seat_limit():
    return db._rows("SELECT seat_limit, active_seats FROM software_subscriptions WHERE subscription_id='SUB001'")[0]


def outbox(kind=None):
    rows = db._rows("SELECT * FROM renewal_outbox")
    return [r for r in rows if kind is None or r["kind"] == kind]


def start():
    return renewal.scheduled_run("2026-07-01", recommender=fake_recommender)


def clear_all():
    for eid in ("IA-WEBEX-APPROVE-001", "FC-WEBEX-CLEAR-001", "SR-WEBEX-REVIEW-001"):
        renewal.ingest_event(EVENTS[eid])


def reply(fixture):
    raw = renewal.ProviderEmailAdapter().fetch_reply(fixture)
    return renewal.ingest_provider_reply(raw, "2026-07-03", extractor=lambda body: PROPOSALS[fixture])


def test_the_schedule_assesses_the_window_and_asks_the_approver():
    out = start()
    cases = {c["contract_id"]: c for c in out["cases"]}
    assert cases["C001"]["urgency"] == "urgent_overdue" and cases["C001"]["notice_deadline"] == "2026-06-05"
    assert cases["C001"]["review_open"] == "2026-04-21" and cases["C001"]["action"] == "expand"
    assert cases["C020"]["action"] == "escalate" and "D_CS" in cases["C020"]["escalation_reason"]   # owner conflict
    assert cases["C017"]["action"] == "escalate"                                                   # ambiguous terms
    assert all(c["next_action"] for c in cases.values())
    assert out["run"]["stage"] == "awaiting_internal_decision" and out["run"]["proposed_scope"]["seat_limit"] == 50
    request = outbox("decision_request")
    assert len(request) == 1 and request[0]["recipient"] == "E006" and request[0]["channel"] == "slack"
    assert not outbox("provider_request")


def test_no_supplier_contact_until_all_three_preconditions_hold():
    start()
    renewal.ingest_event(EVENTS["IA-WEBEX-APPROVE-001"])
    assert renewal.run_state()["stage"] == "awaiting_clearances" and not outbox("provider_request")
    renewal.ingest_event(EVENTS["FC-WEBEX-CLEAR-001"])
    assert db.get_approval("AP002")["status"] == "approved" and not outbox("provider_request")
    renewal.ingest_event(EVENTS["SR-WEBEX-REVIEW-001"])
    assert renewal.run_state()["stage"] == "awaiting_provider_reply"
    assert len(outbox("provider_request")) == 1 and "USD 22,000" in outbox("provider_request")[0]["body"]


def test_a_rejection_keeps_it_with_a_human():
    start()
    renewal.ingest_event(EVENTS["IA-WEBEX-REJECT-001"])
    for eid in ("FC-WEBEX-CLEAR-001", "SR-WEBEX-REVIEW-001"):
        renewal.ingest_event(EVENTS[eid])
    assert renewal.run_state()["status"] == "needs_human" and not outbox("provider_request")


def test_happy_path_records_then_applies_once_on_the_effective_date():
    start(); clear_all()
    r = reply("webex_renewal_approved")
    assert r["outcome"] == "recorded" and renewal.run_state()["stage"] == "confirmed_awaiting_effective_date"
    assert seat_limit()["seat_limit"] == 40 and not outbox("capacity_changed")      # July 3: NOT applied
    renewal.scheduled_run("2026-07-21", recommender=fake_recommender)
    assert seat_limit() == {"seat_limit": 50, "active_seats": 42}                    # active seats not reset
    notes = outbox("capacity_changed")
    assert [n["recipient"] for n in notes] == ["E010"] and "USD" not in notes[0]["body"]
    assert "does not grant access" in notes[0]["body"]
    assert db._rows("SELECT count(*) n FROM audit_log WHERE event_type='renewal_applied'")[0]["n"] == 1


def test_replaying_everything_twice_changes_nothing_twice():
    start(); start(); clear_all(); clear_all()
    reply("webex_renewal_approved"); assert reply("webex_renewal_approved")["duplicate"]
    renewal.scheduled_run("2026-07-21", recommender=fake_recommender)
    renewal.scheduled_run("2026-07-21", recommender=fake_recommender)
    assert len(outbox("decision_request")) == len(outbox("provider_request")) == len(outbox("capacity_changed")) == 1
    assert db._rows("SELECT count(*) n FROM audit_log WHERE event_type='renewal_applied'")[0]["n"] == 1
    assert len(db._rows("SELECT * FROM renewal_events")) == 3


@pytest.mark.parametrize("fixture, why", [
    ("webex_renewal_conditional", "conditional"),
    ("webex_renewal_rejected", "rejected"),
    ("webex_renewal_ambiguous", "ambiguous"),
    ("webex_renewal_over_ceiling", "above the approved ceiling"),
])
def test_anything_but_a_matching_confirmation_goes_to_a_human_with_no_write(fixture, why):
    start(); clear_all()
    r = reply(fixture)
    assert r["outcome"] == "needs_human" and why in r["reason"]
    assert not db._rows("SELECT * FROM renewal_agreements")
    renewal.scheduled_run("2026-07-21", recommender=fake_recommender)
    assert seat_limit()["seat_limit"] == 40 and not outbox("capacity_changed")


def test_an_unconfirmed_delivery_is_uncertain_not_sent():
    start()
    for eid in ("IA-WEBEX-APPROVE-001", "FC-WEBEX-CLEAR-001", "SR-WEBEX-REVIEW-001"):
        renewal.ingest_event(EVENTS[eid], provider=renewal.ProviderEmailAdapter(confirm_delivery=False))
    assert outbox("provider_request")[0]["delivery_status"] == "uncertain"
    assert "not confirmed" in renewal.run_state()["reason"]


def test_reply_fixtures_are_selectable_by_id_or_seed():
    a = renewal.ProviderEmailAdapter()
    assert "RX-WEBEX-2026-8841" in a.fetch_reply("webex_renewal_approved")
    assert a.fetch_reply(seed=7) == a.fetch_reply(seed=7)


def test_runs_without_the_agent():
    code = "import sys, novaops.renewal; assert not any(m.startswith('novaops.agent') for m in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0


def test_a_reply_paired_with_the_wrong_run_is_not_recorded():
    # The golden _readme lists this check as ours to write: a provider reply for ANOTHER renewal.
    start(); clear_all()
    raw = renewal.ProviderEmailAdapter().fetch_reply("webex_renewal_approved").replace(
        "In-Reply-To: <RR-WEBEX-2026@", "In-Reply-To: <RR-ZOOM-2026@")
    r = renewal.ingest_provider_reply(raw, "2026-07-03", extractor=lambda body: PROPOSALS["webex_renewal_approved"])
    assert r["outcome"] == "needs_human" and "RR-ZOOM-2026" in r["reason"]
    assert not db._rows("SELECT * FROM renewal_agreements")


def test_the_submission_runner_carries_the_three_renewal_cases():
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))
    import run_submission
    items = [i for i in run_submission.items(None, optional=True) if "renewal" in i]
    assert [i["id"] for i in items] == ["R-I-01", "R-I-02", "R-I-03"]
    assert items[0]["renewal"]["trigger"] == "2026-07-01" and items[0]["renewal"]["effective"] == "2026-07-21"
    assert [e["event_id"] for e in items[0]["renewal"]["events"]] == [
        "IA-WEBEX-APPROVE-001", "FC-WEBEX-CLEAR-001", "SR-WEBEX-REVIEW-001"]
