# ADR 0008 — Vendor extraction lives outside the agent

Date: 2026-11-12 · Status: accepted

## Context
- **Spec 10:** Workflow 3 takes a document and returns a schema-valid `VendorExtractionResult`.
  It has no caller, no conversation, no permissions and no tools.
- **What is tested:** recognizing that not every LLM feature belongs in the agent. "If deleting
  your whole graph breaks the vendor extractor, the boundary is in the wrong place."

## Decision
- **One module, `novaops/vendor.py`.** It imports only `config` and the model seam `llm.py`.
- **One forced-tool Converse call per source** (`submit_vendor_record`).
- **Everything after the call is code:**
  - dates are normalized to `YYYY-MM-DD`, cost to integer USD, and the enums are mapped;
  - `missing_required_fields` is computed from the nulls and is never taken from the model;
  - there is one follow-up question per missing **required** field (the model's wording, the
    code's list);
  - the result is validated against the supplied schema (Draft 2020-12, with the format
    checker). An invalid result raises, so it is never returned.
- **The model omits a field it cannot find; it does not invent a placeholder.** The forced-tool
  schema has no required properties, so leaving a field out is always possible.
- **Traced as its own `vendor-extraction` span** by `evals/run_submission.py --optional`, with an
  `expected_pass` score for the 0 / 1 / 2 counts. The Langfuse judges target the agent's
  `novaops-turn` span only.

## Consequences
- **`tests/test_vendor.py` proves it without Bedrock:**
  - the 0 / 1 / 2 counts, given correct extractions;
  - normalization;
  - optional omissions;
  - irrelevant detail has no field to land in;
  - an invalid record is refused;
  - importing the module loads no `novaops.agent` code.
- **Not done:** reconciling against the `vendors` and `contracts` tables. Spec 10 places that out
  of scope, and the extractor writes nothing.
