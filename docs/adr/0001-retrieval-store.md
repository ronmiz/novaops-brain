# ADR 0001 — Retrieval: the Lesson 7 OpenSearch pipeline, behind an MCP tool

Date: 2026-11-10 · Status: accepted

## Context
The spec allows any retrieval store (OpenSearch, FAISS, other). In the Lesson 11 session the
instructors said the project brings the Lesson 7 RAG back and exposes it as a tool inside the
MCP server. The corpus is 102 documents in 7 collections; one collection is permission-restricted.

## Options
1. Lesson 10's in-memory FAISS, rebuilt on every server start — free, but a reduced RAG.
2. Lesson 7's OpenSearch Serverless pipeline (pre-filter → k-NN → Nova rerank → dynamic cut).

## Decision
Option 2, in the existing NextGen collection `novaops-rag` (scales to zero when idle), with a
new index `novaops-brain-kb` so the Lesson 7 index stays intact. One tool, `search_documents`,
replaces Lesson 10's two corpus-specific search tools.

Two changes from Lesson 7:
- **Section chunking.** Chunks follow `## ` headings, with 300-word windows and 50-word overlap
  for long sections. GOLDEN-DATASETS states retrieval expectations as document + section, so a
  chunk that knows its section produces precise citations.
- **No subject filter yet.** Lesson 7's Nova subject tagging is not carried over until a
  measurement shows retrieval needs it.

## Consequences
Retrieval is the same code path for every caller; only the filter differs. Re-indexing is
`python -m novaops.rag.store`.
