# NovaOps Company Brain

Final project of the AI Engineer course: an internal assistant over NovaOps' documents,
operational database and governed actions. Built milestone by milestone against
`PROJECT-DESCRIPTION.md`.

| Milestone | Status |
|---|---|
| 1 · Foundation — corpus indexed, database loaded, MCP server, one model seam | ✅ built |
| 2 · Agent loop (classify → scope → evidence → answer, write gate) | ✅ built |
| 3 · Maya (HR & onboarding) | 🔶 built, measuring against S2/S9 |
| 4 · Webex (IT operations) | ⏳ |
| 5 · Observability (Langfuse) | 🔶 tracing bound; scoring next |
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
| One graph: classify → scope → model ↔ tools (+ one rearm) | [`novaops/agent/graph.py`](novaops/agent/graph.py) |
| Scope decides visible tools; no write tool in any loadout | [`novaops/agent/policy.py`](novaops/agent/policy.py) `LOADOUTS`, `select_tools` |
| The ONE function that can release a write — input is an approval record, never message text | [`novaops/agent/write_gate.py`](novaops/agent/write_gate.py) |
| Caller id is an application input: hidden from the model, injected by the tools node | `graph.model_schema`, `graph.build_graph.run_tools` |
| Conversation state survives a restart (SQLite checkpointer) | [`novaops/agent/run.py`](novaops/agent/run.py) |
| Single entry point into the agent | `run.ask()` |
| Distilled named memory carries constraints across turns; unsafe memory rejected | [`novaops/agent/memory.py`](novaops/agent/memory.py), ADR 0005 |
| Maya never files: an action request becomes a typed `AccessRequestIntent`, status `pending` | `graph.handoff`, [`novaops/agent/contracts.py`](novaops/agent/contracts.py) |
| `OnboardingChecklist`: every item cited, citations must exist in tool evidence, blocked needs a reason | `graph.checklist`, `contracts.checklist_errors` |
| Invented citations are detected | `contracts.citation_report` |
| Golden sessions replayed and scored on the binding fields + our own checks | [`evals/golden_replay.py`](evals/golden_replay.py) |
| Every node / Bedrock call / MCP call is a Langfuse span (callback bound to the graph) | `graph.build_graph` (last line) |
| Trace metadata: request_id, caller id+group, scope, intent, loadout, tool sequence, terminal `status`; session = thread | `run.ask` |
| A failure ends as `status: failed` with the reason, never as a fluent answer | `run.ask` |
| Checks for the above | [`tests/test_foundation.py`](tests/test_foundation.py), [`tests/test_agent_loop.py`](tests/test_agent_loop.py), [`tests/test_maya.py`](tests/test_maya.py) |

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
python scripts/check_langfuse.py          # keys reach the Langfuse project
python -m novaops.rag.store               # once: build the index (470 chunks)
python evals/retrieval_eval.py            # retrieval recall + permission boundary
python evals/golden_replay.py             # S1/S2/S9 through the agent (server must run)
python server/server.py                   # terminal 1 — MCP on 127.0.0.1:9880
python scripts/ask.py E010 "Can I use my personal laptop for work?"   # terminal 2: retrieval only
python -m novaops.agent.run E010 "Can I use my personal laptop for work?"          # the agent
python -m novaops.agent.run E010 "What is the status of my Webex login ticket?"
```
