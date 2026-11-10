# NovaOps Company Brain

Final project of the AI Engineer course: an internal assistant over NovaOps' documents,
operational database and governed actions. Built milestone by milestone against
`PROJECT-DESCRIPTION.md`.

| Milestone | Status |
|---|---|
| 1 · Foundation — corpus indexed, database loaded, MCP server, one model seam | ✅ built |
| 2 · Agent loop (classify → scope → evidence → answer, write gate) | ⏳ |
| 3 · Maya (HR & onboarding) | ⏳ |
| 4 · Webex (IT operations) | ⏳ |
| 5 · Observability (Langfuse) | ⏳ |
| 10 · Submission | ⏳ |

## Stack

Python · **Bedrock** (Nova 2 Lite for answers and reranking, Titan V2 for embeddings) ·
**Amazon OpenSearch Serverless** (the Lesson 7 collection `novaops-rag`, new index
`novaops-brain-kb`) · **SQLite** for the operational database · **MCP** (FastMCP,
streamable HTTP) as the tool boundary · Langfuse for tracing (Milestone 5).

## Claims → where they are implemented

| Claim | File |
|---|---|
| Every model call goes through one module | [`novaops/llm.py`](novaops/llm.py) |
| All 102 documents indexed, `audience` metadata preserved | [`novaops/rag/documents.py`](novaops/rag/documents.py), [`novaops/rag/store.py`](novaops/rag/store.py) |
| `manager_playbook` fails closed even without front matter | `documents.audience_for` |
| Manager = some employee's `manager_id` is the caller (not `user_group`) | `db.is_manager` |
| Permission boundary enforced **at retrieval** (pre-filter inside k-NN) | `retrieval.access_clauses` / `retrieval.knn` |
| Filter → k-NN → Nova rerank → dynamic cut (Lesson 7) | [`novaops/rag/retrieval.py`](novaops/rag/retrieval.py) |
| Chunking and final cut chosen by measurement (9/17 → 15/17 expected docs found) | [`docs/adr/0003-chunking-by-measurement.md`](docs/adr/0003-chunking-by-measurement.md), [`evals/retrieval_eval.py`](evals/retrieval_eval.py) |
| Database is a file and can be reseeded | [`novaops/db.py`](novaops/db.py) |
| Tools behind a server boundary | [`server/server.py`](server/server.py) |
| Checks for the above | [`tests/test_foundation.py`](tests/test_foundation.py) |

Design decisions are recorded as ADRs in [`docs/adr/`](docs/adr/); problems hit along the way and how they were solved are in [`docs/OBSTACLES.md`](docs/OBSTACLES.md).

## Permission rule (spec section 12)

A caller is a **manager** when at least one employee's `manager_id` equals the caller's id.
Managers: E004, E006, E012, E013, E018. Everyone else — including unknown ids — retrieves
only `audience: all`. Only `manager_playbook/` is restricted; the five collections without an
`audience` field are unrestricted (absent ≠ deny).

## Data

The supplied dataset is **not** copied into this repository (it contains restricted
documents). `novaops/config.py` reads it from the course folder next to the repo; override
with `NOVAOPS_DATASET_DIR`. Credentials come from the shared `lessons/.env`; see
[`.env.example`](.env.example) for the variable names.

## Run (Windows, Git Bash)

```bash
python -m pip install -r requirements.txt
python -m pytest -q                       # no AWS needed
python -m novaops.rag.store               # once: build the index (470 chunks)
python evals/retrieval_eval.py            # retrieval recall + permission boundary
python server/server.py                   # terminal 1 — MCP on 127.0.0.1:9880
python scripts/ask.py E010 "Can I use my personal laptop for work?"   # terminal 2
```
