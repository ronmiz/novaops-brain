"""Milestone 3 checks that need no AWS: memory safety, the handoff contract, checklist
validation, citation checking, and the golden matcher itself."""
import sys
from pathlib import Path

import pytest

from novaops.agent import contracts, memory, policy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))
import golden_replay  # noqa: E402


# --- memory -----------------------------------------------------------------------

def test_memory_that_drops_a_constraint_is_rejected():
    old = {"active_constraints": ["Q3 SaaS freeze applies"]}
    dropped = memory.ConversationMemory(current_intent="x", important_facts=["E001"], active_constraints=[])
    kept = memory.ConversationMemory(current_intent="x", important_facts=["E001"],
                                     active_constraints=["Q3 SaaS freeze applies"])
    assert not memory.memory_is_safe(old, dropped)
    assert memory.memory_is_safe(old, kept)


def test_empty_memory_is_rejected():
    assert not memory.memory_is_safe({}, memory.ConversationMemory(current_intent="x"))
    assert not memory.memory_is_safe({}, None)


def test_distillation_threshold():
    msgs = ["m"] * 12
    assert memory.needs_distillation(msgs, 0, lambda m: "")
    assert not memory.needs_distillation(msgs, 5, lambda m: "")


# --- handoff ----------------------------------------------------------------------

def test_handoff_carries_traceability_and_never_claims_a_grant():
    intent = contracts.AccessRequestIntent(
        subject_employee_id="E001", subject_name="Maya Cohen", system="Webex",
        justification="CSM customer calls.", requested_by="E004",
        source_thread_id="S2-abc", request_id="req-1")
    text = contracts.handoff_answer(intent).lower()
    assert intent.status == "pending_approval"
    assert "pending" in text and "nothing has been filed" in text and "not been granted" in text


def test_requested_by_comes_from_the_application_not_the_model():
    # The model's proposal schema has no requested_by / thread / request id fields at all.
    assert {"requested_by", "source_thread_id", "request_id"}.isdisjoint(
        contracts.AccessRequestProposal.model_fields)


# --- checklist --------------------------------------------------------------------

EVIDENCE = '{"task_id": "OT005", "status": "blocked"} documents/employment/maya_cohen_offer_letter.md'


def _item(**kw):
    base = dict(item="Webex", category="system", status="blocked", citations=["OT005"],
                blocked_reason="42 of 40 seats")
    return contracts.ChecklistItem(**{**base, **kw})


def test_valid_checklist_has_no_errors():
    p = contracts.ChecklistProposal(employee_id="E001", employee_name="Maya Cohen", items=[
        _item(), _item(item="Laptop", category="equipment", status="planned",
                       citations=["documents/employment/maya_cohen_offer_letter.md"], blocked_reason=None)])
    assert contracts.checklist_errors(p, EVIDENCE) == []


@pytest.mark.parametrize("bad, problem", [
    (dict(citations=[]), "no citation"),
    (dict(citations=["OT999"]), "not in any tool result"),
    (dict(blocked_reason=None), "without a reason"),
])
def test_checklist_validation_catches(bad, problem):
    p = contracts.ChecklistProposal(employee_id="E001", employee_name="Maya Cohen", items=[_item(**bad)])
    assert any(problem in e for e in contracts.checklist_errors(p, EVIDENCE))


# --- citations --------------------------------------------------------------------

def test_invented_citation_is_flagged():
    answer = ("Not allowed [documents/policies/equipment_policy.md § Personal laptops]. "
              "Also [documents/IT_Policies/made_up.md § 1.2] and [record: T001].")
    evidence = "documents/policies/equipment_policy.md ... T001"
    rep = contracts.citation_report(answer, evidence)
    assert rep["has_citation"] and rep["unsupported"] == ["documents/IT_Policies/made_up.md"]


def test_sources_in_tool_output():
    assert contracts.sources_in('{"source": "documents/handbook/making-a-career.md"}') == \
        {"documents/handbook/making-a-career.md"}


# --- policy / golden matcher --------------------------------------------------------

def test_laptop_question_can_see_the_onboarding_checklist():
    # S9 turn 5 needs OT003 (planned 2026-07-26) from the checklist, not just inventory.
    assert "list_onboarding_tasks" in policy.LOADOUTS["equipment_request"]


def test_golden_matcher_alternatives_and_case():
    assert golden_replay.matches("Status: OPEN", "T001|open")
    assert not golden_replay.matches("closed", "T001|open")


def test_golden_checks_flag_a_forbidden_source_and_tool():
    turn = {"n": 1, "forbidden_sources": ["manager_playbook/promotion.md"],
            "forbidden_tools": ["create_access_request"], "should_use_tools": True}
    r = {"answer": "x", "tools_used": ["search_documents"], "citations": {"has_citation": True, "unsupported": []},
         "sources_seen": ["documents/manager_playbook/promotion.md"]}
    checks = golden_replay.check_turn("S9-x", turn, r)
    assert checks["forbidden_sources"][0] is False and checks["forbidden_tools"][0] is True


def test_caller_read_from_persona_when_not_explicit():
    from novaops import db
    db.reseed()
    assert golden_replay.caller_of({"persona": "Rachel Stein (E010, Customer Success) — x"}) == \
        ("E010", "Regular Employee")
    assert golden_replay.caller_of({"caller_id": "E004", "caller_group": "UG_HR", "persona": ""}) == \
        ("E004", "HR Group")


# --- fixes from the first golden run (docs/OBSTACLES.md #10) -------------------------

def test_guessed_employee_id_is_refused():
    known = 'user: Rachel Stein pinged me ... [tool get_employee] {"employee_id": "E010"}'
    assert policy.unverified_employee_id({"employee_id": "E002"}, "E004", known) == "E002"
    assert policy.unverified_employee_id({"employee_id": "E010"}, "E004", known) is None
    assert policy.unverified_employee_id({"employee_id": "E004"}, "E004", "") is None   # own id
    assert policy.unverified_employee_id({"query": "Rachel"}, "E004", "") is None       # no id arg


def test_every_tool_row_carries_its_own_citation():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
    import server
    assert server.cited([{"task_id": "OT005"}], "task_id")[0]["cite"] == "[record: OT005]"


def test_honest_refusal_with_no_evidence_is_not_a_citation_failure():
    turn = {"n": 4}
    refusal = {"answer": "That is available to managers only.", "tools_used": ["search_documents"],
               "evidence_returned": False, "citations": {"has_citation": False, "unsupported": []}}
    assert "citations" not in golden_replay.check_turn("S9-x", turn, refusal)
    uncited = {**refusal, "evidence_returned": True}
    assert golden_replay.check_turn("S9-x", turn, uncited)["citations"][0] is False


@pytest.mark.parametrize("kind, needs", [("lookup", True), ("recall", False), ("summary", False),
                                         ("draft", False), ("pasted_text", False), ("action", False)])
def test_only_a_lookup_gathers_evidence(kind, needs):
    # Code derives requires_tools from the request type; the model no longer chooses it (#12).
    assert policy.TurnPlan(current_intent="other", request_type=kind).requires_tools is needs
    assert "requires_tools" not in policy.TurnPlan.model_json_schema()["properties"]


def test_user_rules_are_labelled_as_rules_not_causes():
    text = policy.render_plan(policy.TurnPlan(current_intent="other",
                                              relevant_constraints=["Q3 SaaS freeze applies"]))
    assert "NOT facts" in text and "never the cause" in text


# --- fixes from the second golden run (docs/OBSTACLES.md #11) ------------------------

def test_name_passed_as_employee_id_is_refused():
    assert policy.unverified_employee_id({"employee_id": "Rachel Stein"}, "E004", "Rachel Stein") == "Rachel Stein"


@pytest.mark.parametrize("answer, cited", [
    ("x [record: OT005]", ["OT005"]),
    ("x [cite: documents/employment/maya_cohen_offer_letter.md]", ["documents/employment/maya_cohen_offer_letter.md"]),
    ("x [record: documents/handbook/making-a-career.md § Promotion Process]", ["documents/handbook/making-a-career.md"]),
])
def test_citation_forms_are_recognised(answer, cited):
    rep = contracts.citation_report(answer, "OT005 documents/employment/maya_cohen_offer_letter.md "
                                            "documents/handbook/making-a-career.md")
    assert rep["has_citation"] and sorted(rep["cited_documents"] + rep["cited_records"]) == cited
    assert rep["unsupported"] == []


def test_vague_bracket_is_not_a_citation():
    assert not contracts.citation_report("x [cite: employee record]", "")["has_citation"]


# --- run 4: verify the planner's no-lookup claims (docs/OBSTACLES.md #13) ------------

GROUNDING = ("user: She starts 2026-08-01, she's hybrid based in Israel\n"
             'tool: {"text": "Owner: IT ... IT must approve and log the exception"}')


def _recall(quote):
    return policy.TurnPlan(current_intent="other", request_type="recall", answer_quote=quote)


def test_recall_with_a_real_quote_stands():
    assert policy.verify_request_type(_recall("hybrid based in Israel"),
                                      "remind me where she is based", GROUNDING).request_type == "recall"


@pytest.mark.parametrize("quote, message", [
    ("", "which team owns it?"),                                        # no quote
    ("Finance approval above USD 7,500", "does a seat need Finance?"),  # quote not in the conversation
    ("Owner: IT", "who owns it right now?"),                            # asks for the current state
])
def test_unverified_recall_becomes_a_lookup(quote, message):
    assert policy.verify_request_type(_recall(quote), message, GROUNDING).request_type == "lookup"


def test_pasted_text_needs_something_pasted():
    plan = policy.TurnPlan(current_intent="other", request_type="pasted_text")
    assert policy.verify_request_type(plan, "what is mine?", "").request_type == "lookup"
    assert policy.verify_request_type(plan, "what is mine?\n> a\n> b\n> c", "").request_type == "pasted_text"


# --- run 7: verification bugs (docs/OBSTACLES.md #16) --------------------------------

def test_quote_spanning_a_json_line_break_matches():
    tool_json = r'{"text": "Personal laptops are not allowed for employees, with one narrow exception: a\nfive-business-day IT continuity exception"}'
    plan = _recall("narrow exception: a five-business-day IT continuity exception")
    assert policy.verify_request_type(plan, "does IT need to sign it off?", tool_json).request_type == "recall"


def test_quote_from_session_memory_is_accepted():
    memory_text = "Established facts:\n  - Maya Cohen starts 2026-08-01, hybrid, based in Israel"
    plan = _recall("starts 2026-08-01, hybrid, based in Israel")
    assert policy.verify_request_type(plan, "remind me where she is based", memory_text).request_type == "recall"


# --- runs 8a-8c: mean of three (docs/OBSTACLES.md #17) --------------------------------

def test_quote_with_a_copied_citation_still_matches():
    tool_json = '{"text": "IT must approve and log the exception before the employee uses a personal machine"}'
    plan = _recall("IT must approve and log the exception​​[documents/policies/equipment_policy.md § (whole document)]")
    assert policy.verify_request_type(plan, "does IT need to sign it off?", tool_json).request_type == "recall"


def test_a_webex_seat_asked_as_equipment_can_reach_the_subscription():
    assert "check_software_subscription" in policy.LOADOUTS["equipment_request"]


def test_quote_of_several_excerpts_is_checked_line_by_line():
    memory_text = "Established facts:\n  - Maya Cohen location=Israel\n  - Maya Cohen start_date=2026-08-01"
    ok = _recall("Maya Cohen location=Israel\nMaya Cohen start_date=2026-08-01")
    bad = _recall("Maya Cohen location=Israel\nMaya Cohen start_date=2026-09-01")
    assert policy.verify_request_type(ok, "remind me", memory_text).request_type == "recall"
    assert policy.verify_request_type(bad, "remind me", memory_text).request_type == "lookup"


# --- round 10: last-resort sources, pinned clock (docs/OBSTACLES.md #19) -------------

def test_application_attaches_the_records_an_uncited_answer_names():
    ev = '[{"ticket_id": "T001", "cite": "[record: T001]"}] {"employee_id": "E010"}'
    out = contracts.attach_sources("Rachel's ticket (T001) is open; see also T999.", ev)
    assert out.endswith("Sources: [record: T001]")          # T999 never came back from a tool
    assert contracts.attach_sources("Open [record: T001].", ev) == "Open [record: T001]."


def test_uncited_answer_without_ids_gets_this_turns_documents():
    ev = '{"source": "documents/handbook/making-a-career.md", "text": "..."}'
    assert "[documents/handbook/making-a-career.md]" in contracts.attach_sources("Day 60: meaningful work.", ev)
    assert contracts.attach_sources("Nothing here.", "") == "Nothing here."


def test_clock_is_pinned_to_the_dataset_day():
    from novaops import config
    assert config.TODAY == "2026-07-01"
    assert "2026-07-01" in policy.ANSWER_PROMPT.format(caller_id="E010", caller_group="x", today=config.TODAY)


def test_an_eligibility_question_can_see_the_joiners_onboarding_tasks():
    # M-I-03 "Is Maya Cohen eligible for remote work equipment?" read as an employee lookup (#23)
    assert "list_onboarding_tasks" in policy.LOADOUTS["employee_lookup"]
    assert "Eligibility is not delivery" in policy.ANSWER_PROMPT


def test_a_pasted_thread_answer_keeps_only_the_callers_items():
    a = ("Your two items:\n1. Sign the equipment responsibility form [forwarded thread]\n"
         "2. Finish your BambooHR profile [forwarded thread]\n\n"
         "Everything else (Okta groups, Datadog renewal, Webex seat) belongs to IT or Yael [forwarded thread].")
    out = contracts.only_theirs(a)
    assert "Datadog" not in out and "BambooHR" in out and out.endswith("[forwarded thread]")
