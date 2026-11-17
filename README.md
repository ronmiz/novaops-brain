# NovaOps Company Brain

Final project of the AI Engineer course: an internal assistant over NovaOps' documents,
operational database and governed actions. Built milestone by milestone against
`PROJECT-DESCRIPTION.md`.

| Milestone | Status |
|---|---|
| 1 · Foundation — corpus indexed, database loaded, MCP server, one model seam | ✅ built |
| 2 · Agent loop (classify → scope → evidence → answer, write gate) | ✅ built |
| 3 · Maya (HR & onboarding) | ✅ golden S1/S2/S9: 8/21 baseline → mean 17.67/21 over 3 runs → 19/21 |
| 4 · Webex (IT operations) | ✅ W-I-01/02/03 live; pause → approve in a new process → resume = one trace; S6/S8 8/8 (noise delta 0) |
| 5 · Observability (Langfuse) | ✅ tracing, 3 Langfuse judges, `golden_pass` / `expected_pass` scores |
| 6 · Vendor (optional) | ✅ V-I-01/02/03 live: missing required fields 0 / 1 / 2 as specified, schema-valid |
| 7 · Renewal (optional) | ✅ R-I-01 applied on 07-21 (seat limit 50, Rachel notified); R-I-02 conditional and R-I-03 ambiguous → needs_human, seat limit 40 |
| 9 · Packaging (optional) | 🔶 API + worker + Dockerfile + Compose; entry-point tests pass, container run pending |
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
| Clock pinned to the dataset day (2026-07-01) | `config.TODAY` |
| Webex consumes the handoff: a model-free approval workflow that pauses in `interrupt()` on its own SQLite thread | [`novaops/agent/approval.py`](novaops/agent/approval.py), ADR 0006 |
| A write is released only against the approval ROW (the resume payload is ignored); the server refuses it too | `approval.wait`/`release`, `write_gate.released_writes`, `db.create_access_request` |
| Idempotent, audited writes: T001 / AR001 / AP001 reused, replay creates no row | `db.request_approval`, `db.create_access_request`, `tests/test_webex.py` |
| Approval survives process death; only the named approver can decide | [`novaops/approve.py`](novaops/approve.py), `db.record_approval` |
| `AccessDecision`: facts / actions / next steps, built from records, never claims a grant | `contracts.AccessDecision`, `approval.build_decision`, `contracts.claims_granted` |
| The missing capability: seat assignments are not recorded (W-I-02) | `server.check_team_system_access`, `db.team_system_access` |
| LLM judges registered in Langfuse (faithfulness, citation_quality, no_overclaim), one per turn on the `novaops-turn` span | [`evals/register_judges.py`](evals/register_judges.py), ADR 0007 |
| The judge's evidence is on the span it reads (`$.trajectory.calls` / `.state`) | `run.trajectory` |
| Deterministic score `golden_pass` written onto each replayed turn's trace | `evals/golden_replay.py` |
| Read a trace back as text (v2 API) | [`scripts/show_trace.py`](scripts/show_trace.py) |
| A closed branch must not drive later tool choice (S3); a turn-1 rule still binds on S4 t5/t7 | `golden_replay.CLOSED_BRANCH`, `CONSTRAINT_CARRY` |
| Our own expected answers for the 27 submission turns, scored onto each trace as `expected_pass` | [`evals/expected_inputs.json`](evals/expected_inputs.json), [`evals/run_submission.py`](evals/run_submission.py) |
| Submission run follows spec 13 (reseed per case, one thread per session, pinned clock, one trace per turn) and fills the trace index | `evals/run_submission.py` |
| Project-level agent control: a hook that blocks weakening tests; skills for measuring and logging | [`.claude/settings.json`](.claude/settings.json), [`.claude/hooks/protect_tests.py`](.claude/hooks/protect_tests.py), [`.claude/skills/`](.claude/skills/) |
| Workflow 3 (Vendor) is NOT agent work: one forced-tool Converse call, code-computed missing fields, schema-validated | [`novaops/vendor.py`](novaops/vendor.py), ADR 0008, [`tests/test_vendor.py`](tests/test_vendor.py) |
| Workflow 4 (Renewal): scheduled, event-driven, survives process death; the model recommends and extracts, code decides and writes | [`novaops/renewal.py`](novaops/renewal.py), ADR 0009, [`tests/test_renewal.py`](tests/test_renewal.py) |
| Thin validated HTTP entry points over the SAME core functions; `/health` and `/ready` never call a model | [`novaops/api.py`](novaops/api.py), [`tests/test_packaging.py`](tests/test_packaging.py) |
| Renewal worker is a separate entry point (event plane) from the API (request plane) | [`novaops/worker.py`](novaops/worker.py) |
| One non-root image, three services, commit-SHA tags, dataset mounted read-only, no secrets in the repo | [`Dockerfile`](Dockerfile), [`compose.yaml`](compose.yaml) |
| Checks for the above | [`tests/test_foundation.py`](tests/test_foundation.py), [`tests/test_agent_loop.py`](tests/test_agent_loop.py), [`tests/test_maya.py`](tests/test_maya.py), [`tests/test_webex.py`](tests/test_webex.py), [`tests/test_observability.py`](tests/test_observability.py), [`tests/test_harness.py`](tests/test_harness.py), [`tests/test_vendor.py`](tests/test_vendor.py), [`tests/test_renewal.py`](tests/test_renewal.py) |

## Measured: a judge and a check that disagree (Lesson 11)

`runs/m5-scores-s1.txt`, S1 turn 2: `golden_pass = 0`, all three judges `1.0`. Both are right:
the answer was faithful, well cited and claimed nothing — but it re-fetched a policy it already
had (`should_use_tools: false` is binding). The judges score the *answer*; the deterministic
check scores the *process*. Neither alone would show both.

## Deliberate deviation from the golden set

S2 turn 10 ("go ahead and file") is recorded with `should_use_tools: false`, and its note says the
handoff "crosses once into the separate Webex workflow and returns its pending result". Here the
Maya graph calls no tool on that turn: it emits the typed `AccessRequestIntent`. The Webex approval
workflow then reads the records and files (or reuses) the approval request in the same turn, under
its own `approval-workflow` span, and returns `pending`. Our scorer counts those reads as the turn's
tools, so it reports this turn as a miss, and we leave it visible rather than redefine the check.

## Course stages (spec 15–16)

| Stage | Status | Evidence |
|---|---|---|
| Lesson 11 — observability and evals (required) | ✅ | tracing bound to the graph; trace metadata; `golden_pass` / `expected_pass` scores; 3 Langfuse judges (ADR 0007) |
| Lesson 12 — eval loop engineering | ✅ | the improvement log below: honest baseline first, one change per measured round, a gate the loop cannot cheat (`pytest` + `.claude/hooks/protect_tests.py`), a human accepted every change, before/after in `docs/OBSTACLES.md` |
| Lesson 13 — guardrails | not part of this project (spec 13) | — |
| Lesson 14 — packaging and deployment | ✅ (Compose demo; LiteLLM not used) | `novaops/api.py`, `novaops/worker.py`, `Dockerfile`, `compose.yaml` |

### Improvement log (golden S1/S2/S9, 21 turns)

| Round | Change (docs/OBSTACLES.md) | Score |
|---|---|---|
| baseline | first full agent | 8/21 |
| 2–3 | id guard, `cite` on every record, request types (#10–12) | 12 → 16 |
| 4–7 | verified recall, forced tool use, verifier bugs (#13–16) | 15 → 14 → 16 → 17 |
| 8 (3 runs) | measured as a mean from here on | mean 15.0 |
| 9 (3 runs) | quote citation strip, subscription tool, pasted-thread rule (#17) | mean 16.0 |
| 10 (3 runs) | per-line quote check, threshold/date rules (#18) | mean 17.67 |
| 11 | app-attached sources, recite on invented citation, pinned clock (#19) | 19/21 |

 in [`docs/adr/`](docs/adr/); problems hit along the way and how they were solved are in [`docs/OBSTACLES.md`](docs/OBSTACLES.md).

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
python -m novaops.agent.run E010 "I joined Customer Success and need Webex access. Webex says my account is not licensed."
python -m novaops.approve AP001 --by E006 --approve --reason "IT approves"   # a new process resumes the pause
```
