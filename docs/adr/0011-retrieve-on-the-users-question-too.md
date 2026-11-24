# ADR 0011 — Retrieve on the user's own question as well as the model's query

Date: 2026-11-24 · Status: accepted

## Context
`search_documents` received only the query the model wrote. For a two-part question ("How do I
get promoted here? What does the path look like for a CSM?") the model searched one paraphrase
and lost the first half. The promotion-cycle section never reached the reranker (#37,
`runs/m10-trace-ms02t1.txt`). The failure is in what retrieval was ASKED, so no change to the
cut or the reranker could recover it.

## Decision
- The application fills a `question` argument on `search_documents` with the current turn's
  user message (capped at 1,500 characters). It fills it exactly like `caller_id`. The model
  never sees it (`policy.APP_ARGS`, `graph.model_schema`).
- `retrieval.candidates()` runs k-NN on the model's query AND on the question, each with the
  same permission filter. The two candidate sets are merged and deduplicated.
- The reranker scores against `"<question>\n(search focus: <model query>)"`. The user's
  actual need comes first; the model's focus still separates sub-questions.
- No question (scripts, the approval workflow) means exactly the old behaviour.

## Consequences
- Recall no longer depends on the model's paraphrase. A user cannot make the model fetch
  something the permission filter forbids: the filter is unchanged and applies to both queries.
- One extra embedding per search, and up to ~40 candidates in the rerank call instead of ~20:
  more tokens and latency per search.
- Measured on the golden sessions before the final run, like every change (#36).
