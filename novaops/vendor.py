"""Workflow 3 — Vendor CRM extraction (optional, spec section 10).

Standalone on purpose: no agent, no LangChain, no tools, no database. A procurement document
in, a validated `VendorExtractionResult` out. It imports only the model seam (`llm.py`) and
the config — delete the whole agent package and this still runs.

    one Converse call, forced `submit_vendor_record` tool  (the model reads)
    -> normalize: dates YYYY-MM-DD, cost integer USD, enums  (code)
    -> missing_required_fields from the nulls                 (code, never the model)
    -> one follow-up question per missing REQUIRED field      (model's wording, code's list)
    -> validate against the supplied JSON Schema              (code; invalid = an exception)

    python -m novaops.vendor <source.md> [<source.md> ...]
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from . import config, llm

VENDOR_DIR = config.DATASET_DIR / "workflows" / "vendor"
SCHEMA = json.loads((VENDOR_DIR / "schemas" / "vendor_extraction_result.schema.json").read_text(encoding="utf-8"))
RECORD = SCHEMA["$defs"]["vendor_crm_record"]
FIELDS = RECORD["required"]                                        # every key, in schema order
REQUIRED = SCHEMA["$defs"]["required_field_name"]["enum"]          # the CRM-required subset
SOURCE_TYPES = {"intake": "formal_document", "form": "formal_document", "email": "email_chain",
                "transcript": "call_transcript", "call": "call_transcript"}

SYSTEM = (
    "You extract a vendor CRM record from ONE procurement document. Call submit_vendor_record once.\n"
    "- Fill a field ONLY when the document states it. If it does not, OMIT the field. Never guess from "
    "the vendor's name, category or industry convention.\n"
    "- A statement that something is NOT required is a value: security_review_required = false.\n"
    "- annual_cost_usd: the yearly cost as a plain integer number of US dollars (write words as digits).\n"
    "- Dates exactly as written; code normalizes them.\n"
    "- vendor_name is the display name; legal_name only if the registered legal company name is stated.\n"
    "- Ignore marketing, scheduling, anecdotes and anything that is not a field below.\n"
    "- follow_up_questions: one short, specific question for each REQUIRED field you omitted, "
    "addressed to the vendor contact.\n"
    "- conflicts: only when the document states two different values for the same field."
)

_STR = {"type": "string"}
TOOL = {"toolSpec": {
    "name": "submit_vendor_record",
    "description": "Submit the vendor CRM record extracted from the document.",
    "inputSchema": {"json": {
        "type": "object",
        "properties": {
            **{f: {**_STR, "description": "Omit if not stated."} for f in FIELDS},
            "annual_cost_usd": {"type": "integer", "description": "Yearly cost in USD. Omit if not stated."},
            "security_review_required": {"type": "boolean", "description": "Omit if not stated."},
            "renewal_type": {**_STR, "enum": ["automatic", "manual", "usage_based", "ambiguous"]},
            "data_sensitivity": {**_STR, "enum": ["Public", "Internal", "Confidential", "Restricted",
                                                  "Highly Restricted"]},
            "follow_up_questions": {"type": "object",
                                    "description": "Required field name -> question, for omitted required fields.",
                                    "additionalProperties": _STR},
            "conflicts": {"type": "array", "items": _STR},
        },
    }},
}}

_DATE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y", "%B %d %Y", "%d/%m/%Y")


def normalize_date(value) -> str | None:
    if not value:
        return None
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(value).strip())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None                     # unparseable is unstated, not a guess


def normalize_cost(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    return int(float(digits)) if digits else None


def normalize_renewal(value) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in ("automatic", "manual", "usage_based", "ambiguous"):
        return text
    # "manual, not automatic" is manual: check the negated form before the bare word
    if "manual" in text or "not automatic" in text:
        return "manual"
    return "automatic" if "auto" in text else "usage_based" if "usage" in text else "ambiguous"


def normalize_sensitivity(value) -> str | None:
    allowed = {s.lower(): s for s in RECORD["properties"]["data_sensitivity"]["enum"] if s}
    return allowed.get(str(value or "").strip().lower())


def normalize_bool(value) -> bool | None:
    if isinstance(value, bool) or value is None:
        return value
    return {"yes": True, "true": True, "required": True, "no": False, "false": False,
            "not required": False}.get(str(value).strip().lower())


def build_result(raw: dict, source_id: str, source_type: str) -> dict:
    """Everything after the model call: deterministic, testable without Bedrock."""
    record = {f: (str(raw[f]).strip() or None) if isinstance(raw.get(f), str) else raw.get(f) for f in FIELDS}
    record["annual_cost_usd"] = normalize_cost(raw.get("annual_cost_usd"))
    record["contract_start_date"] = normalize_date(raw.get("contract_start_date"))
    record["contract_end_date"] = normalize_date(raw.get("contract_end_date"))
    record["renewal_type"] = normalize_renewal(raw.get("renewal_type"))
    record["data_sensitivity"] = normalize_sensitivity(raw.get("data_sensitivity"))
    record["security_review_required"] = normalize_bool(raw.get("security_review_required"))
    missing = [f for f in REQUIRED if record[f] is None]
    asked = raw.get("follow_up_questions") or {}
    questions = [{"field": f, "question": (asked.get(f) or "").strip()
                  or f"Could you confirm the {f.replace('_', ' ')} for this vendor?"} for f in missing]
    result = {"source_id": source_id, "source_type": source_type, "record": record,
              "missing_required_fields": missing, "conflicts": [c for c in raw.get("conflicts") or [] if c],
              "follow_up_questions": questions}
    errors = sorted(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(result),
                    key=lambda e: list(e.path))
    if errors:
        raise ValueError("VendorExtractionResult failed schema validation: "
                         + "; ".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors))
    return result


def source_type_of(name: str) -> str:
    return next((t for key, t in SOURCE_TYPES.items() if key in name.lower()), "formal_document")


def extract(document: str, source_id: str, source_type: str | None = None) -> dict:
    """One model call per source, then code. Raises ValueError if the result is invalid."""
    raw = llm.converse(f"Document ({source_id}):\n\n{document}", system=SYSTEM, tool=TOOL, max_tokens=1500)
    return build_result(raw, source_id, source_type or source_type_of(source_id))


def main(paths: list[str]) -> None:
    for p in paths or sorted(str(x) for x in (VENDOR_DIR / "sources").glob("*.md")):
        path = Path(p)
        result = extract(path.read_text(encoding="utf-8"), path.stem)
        print(f"{path.stem}: missing {result['missing_required_fields']}")
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
