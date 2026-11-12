"""Workflow 3 (Vendor) without Bedrock: the code after the one model call, and the boundary."""
import subprocess
import sys

import pytest

from novaops import vendor

# What a correct model call returns for each supplied source (omitted = not stated).
HELIODESK = {"vendor_name": "HelioDesk", "legal_name": "HelioDesk Technologies Ltd.",
             "primary_contact_name": "Ava Patel", "primary_contact_email": "ava.patel@heliodesk.example",
             "service_category": "Customer support quality assurance SaaS",
             "internal_owner_department": "Customer Success", "annual_cost_usd": "USD 28,800",
             "contract_start_date": "October 1, 2026", "contract_end_date": "September 30, 2027",
             "renewal_type": "Manual renewal", "payment_terms": "Net 30 days from invoice",
             "data_sensitivity": "confidential", "security_review_required": "Yes",
             "website": "https://www.heliodesk.example", "contact_phone": "+44 20 7946 0281",
             "headquarters": "London, United Kingdom", "implementation_notes": "Pilot: twenty SupportDesk agents."}
ROUTEPILOT = {"vendor_name": "RoutePilot", "legal_name": "RoutePilot Systems Inc.",
              "primary_contact_name": "Miguel Santos", "primary_contact_email": "miguel.santos@routepilot.example",
              "service_category": "SaaS spend and renewal analytics", "internal_owner_department": "Finance",
              "annual_cost_usd": 18600, "contract_start_date": "15 November 2026",
              "contract_end_date": "14 November 2027", "renewal_type": "automatically renews",
              "data_sensitivity": "Internal", "security_review_required": False,
              "follow_up_questions": {"payment_terms": "What are the invoice payment terms?"}}
CIPHERNEST = {"vendor_name": "CipherNest", "primary_contact_name": "Nora Fischer",
              "primary_contact_email": "nora.fischer@ciphernest.example", "contact_phone": "+49 30 5557 0184",
              "service_category": "Secure managed file-transfer software", "internal_owner_department": "IT",
              "annual_cost_usd": 31200, "contract_start_date": "December 1, 2026",
              "contract_end_date": "November 30, 2027", "renewal_type": "manual, not automatic",
              "payment_terms": "Net 45 days", "data_sensitivity": "Restricted"}


@pytest.mark.parametrize("raw, source, missing", [
    (HELIODESK, "formal_vendor_intake", []),
    (ROUTEPILOT, "procurement_email_chain", ["payment_terms"]),
    (CIPHERNEST, "discovery_call_transcript", ["legal_name", "security_review_required"]),
])
def test_zero_one_two_missing_required_fields(raw, source, missing):
    r = vendor.build_result(raw, source, vendor.source_type_of(source))       # validates against the schema
    assert r["missing_required_fields"] == missing
    assert [q["field"] for q in r["follow_up_questions"]] == missing
    assert set(r["record"]) == set(vendor.FIELDS)                             # every key present, null if unstated


def test_normalization():
    r = vendor.build_result(HELIODESK, "formal_vendor_intake", "formal_document")["record"]
    assert (r["annual_cost_usd"], r["contract_start_date"], r["renewal_type"]) == (28800, "2026-10-01", "manual")
    assert (r["data_sensitivity"], r["security_review_required"]) == ("Confidential", True)
    c = vendor.build_result(CIPHERNEST, "discovery_call_transcript", "call_transcript")["record"]
    assert c["renewal_type"] == "manual" and c["security_review_required"] is None


def test_an_absent_optional_field_creates_no_follow_up():
    r = vendor.build_result(ROUTEPILOT, "procurement_email_chain", "email_chain")
    assert r["record"]["website"] is None and "website" not in r["missing_required_fields"]


def test_irrelevant_detail_has_nowhere_to_go():
    r = vendor.build_result({**HELIODESK, "logo": "purple lighthouse", "award": "2025"}, "x", "formal_document")
    assert "logo" not in r["record"] and "purple" not in str(r)


def test_an_invalid_record_is_refused_not_returned():
    with pytest.raises(ValueError):
        vendor.build_result({**HELIODESK, "primary_contact_email": "not-an-email"}, "x", "formal_document")


def test_runs_without_the_agent():
    code = "import sys, novaops.vendor; assert not any(m.startswith('novaops.agent') for m in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0


def test_the_submission_runner_carries_the_three_vendor_cases():
    import sys as _s
    from pathlib import Path
    _s.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))
    import run_submission
    vendor_items = [i for i in run_submission.items(None, optional=True) if "vendor" in i]
    assert [i["id"] for i in vendor_items] == ["V-I-01", "V-I-02", "V-I-03"]
    assert [len(run_submission.EXPECTED["inputs"][i]["missing_required_fields"]) for i in
            ("V-I-01", "V-I-02", "V-I-03")] == [0, 1, 2]
