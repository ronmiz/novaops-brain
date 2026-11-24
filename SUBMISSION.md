# NovaOps final project — submission

Fill this in and commit it to your repository as `SUBMISSION.md`. It is the first thing read,
and it is how every trace gets found.

---

## 1. Repository

| | |
| ------------------- | ------------------------------------------------ |
| **Repository URL**  | `https://github.com/ronmiz/novaops-brain` |
| **Access**          | public |
| **Commit reviewed** | `e7a60c3bba7cf7250cc3c08675965247af16c81b` |

## 2. Langfuse

| | |
| ------------------ | --------------------------------------------- |
| **Host region**    | `cloud.langfuse.com` EU |
| **Project name**   | My Project (organization: Ron's Organization) |
| **Instructor role**| Member *(required — traces are read through the API)* |
| **Invitation accepted** | yes / no |

## 3. Scope completed

| Workflow | Built | Notes |
| --------------------------- | ------ | ----- |
| 1 — Maya · HR and onboarding | required | ✅ `novaops/agent/` (graph, policy, memory, contracts); golden S1/S2/S9 replayed by `evals/golden_replay.py` |
| 2 — Webex · IT operations    | required | ✅ `novaops/agent/approval.py`, `novaops/approve.py`, `novaops/agent/write_gate.py`; ADR 0006 |
| 3 — Vendor · CRM extraction  | yes | ✅ `novaops/vendor.py` (standalone, one forced-tool call, schema-validated); V-I-01/02/03 → 0/1/2 missing; ADR 0008 |
| 4 — Renewal · contract renewal | yes | ✅ `novaops/renewal.py` (persisted state machine, CLI + `novaops/worker.py`); R-I-01 applied, R-I-02/03 needs_human; ADR 0009 |

| Optional stage | Done | Evidence |
| ------------------------------- | -------- | -------- |
| Lesson 12 — loop engineering     | yes | `.claude/hooks/protect_tests.py` (+ `tests/test_harness.py`), `.claude/skills/measure`, `.claude/skills/log-obstacle`; README "Improvement log"; `docs/OBSTACLES.md` #1–#39 with before/after runs in `runs/` |
| Lesson 14 — packaging and deploy | partial | `novaops/api.py` (validated, `/health` `/ready` without model calls), `novaops/worker.py`, non-root `Dockerfile`, `compose.yaml`, `tests/test_packaging.py`. Containers not yet run: Docker Desktop needs an IT-approved Windows feature on the build machine |

## 4. Durable-behavior evidence

Some required behavior cannot be seen in a single trace. Point at the commit, test, or trace
that proves each — one line, or "not attempted".

| Check | Evidence |
| ------------------------------------------------------------- | -------- |
| Replaying a request creates no second ticket or access request | `tests/test_webex.py::test_replaying_the_request_creates_nothing`, `::test_approved_replay_reuses_ar001_and_creates_no_row`; live: W-I-03 / W-S-01 t4 reuse T001, AR001, AP001 |
| A pending approval survives the process being killed and restarted | `tests/test_webex.py::test_survives_process_death_and_releases_only_on_the_record`; live: `runs/m4-trace-wi03.txt` (pause, approve from a new process with `python -m novaops.approve`, resume = one trace) |
| The write gate releases only against a recorded approval | `novaops/agent/write_gate.py`; `tests/test_webex.py::test_write_is_refused_without_a_recorded_approval`, `::test_resume_without_a_recorded_decision_stays_paused`, `::test_writes_and_app_tools_never_reach_a_model`; W-S-01 t4 ("GO AHEAD") stays `pending` |
| *Renewal (optional): every event replayed twice leaves one update and one notification per recipient* | `tests/test_renewal.py::test_replaying_everything_twice_changes_nothing_twice`; `runs/m7-renewal-processes.txt` (separate processes, read back from persisted records) |

## 5. Trace index

One row per item in `EVALUATION-INPUTS.yaml` — 27 required, 33 with both optional workflows.
**Fill in the trace id column only**; the ids and turn numbers are already correct. Leave a row
blank if you did not run it.


### Maya - HR and onboarding

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `M-I-01` | — | `914a84474b0293cc28ea3690d2383227` |
| `M-I-02` | — | `5c513b341c870eaad5dd98a20b6e0656` |
| `M-I-03` | — | `e8c7940c8c179a7316ac496a32527ae5` |
| `M-S-01` | 1 | `f5d89383303633d3dd1a91783f475820` |
| `M-S-01` | 2 | `7978f3a52625dfa4c2f11bef72e04dbd` |
| `M-S-01` | 3 | `cf4360cf3cd70001e143475997c7de2a` |
| `M-S-01` | 4 | `e40e36632de028fbec81fdfcc42ceec7` |
| `M-S-01` | 5 | `376b2cb419bd2481d465e3b9711cb607` |
| `M-S-01` | 6 | `bb43946a292b88f107bf85817b37dd60` |
| `M-S-01` | 7 | `b11782805a94f2cf04912b84379390f6` |
| `M-S-01` | 8 | `e27ff77679f679bb35d524366c4ab068` |
| `M-S-01` | 9 | `28652b5f7fe64c0b62ba5f5c776f9c9f` |
| `M-S-01` | 10 | `be6cb6ab3889b47ebd31b6fd576d876a` |
| `M-S-01` | 11 | `7c127bd8acb9e1969832065edbd011f8` |
| `M-S-01` | 12 | `1f70747b07fcb07c0f495503e3fca1e2` |
| `M-S-02` | 1 | `0e84d1cf1af9805d10c63f6673025219` |
| `M-S-02` | 2 | `9fd275cfa1d44f1a9e36c4a0051c988e` |
| `M-S-02` | 3 | `5745ca927c03d2cd4d20587a1b0ebf74` |
| `M-S-02` | 4 | `3abf70567c9872b2d5dddbfb8d485860` |
| `M-S-02` | 5 | `a0f54cc028860339e2d0138499a9d3a2` |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | `4a233e889c13939dae5cc4b2c6baa581` |
| `W-I-02` | — | `c3caa4221e397bd747bdb0566be6bd96` |
| `W-I-03` | — | `d5984fb42d86fe4178498f7bf1f94657` |
| `W-S-01` | 1 | `6f32762171c0edc750967e2c65b83c5e` |
| `W-S-01` | 2 | `14f6cfd5797f1f5ea7da12114fa7d6ac` |
| `W-S-01` | 3 | `21af065388fa2bc3d53d877f3f861dce` |
| `W-S-01` | 4 | `0b3052b9103e17384df53ff0a3fcc120` |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | `f1950034811ae73c8b702712e77d39aa` |
| `V-I-02` | — | `5e3099dec73f120116908ead93bdd211` |
| `V-I-03` | — | `559c4d6f4d2eb66170bd69781286512b` |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | `c377e8d6a34dc509522e5b43876f7e9e` |
| `R-I-02` | — | `59b1122e30c9112845e28ba429d87bcb` |
| `R-I-03` | — | `cf1e018ee70772a17d72b1a218e2edc9` |

---

## 6. Anything I should know

- **Deliberate deviation, `M-S-01` t10** ("go ahead and file"): Maya calls no tool and emits the
  typed `AccessRequestIntent`. The Webex approval workflow then reads the records and files (or
  reuses) the approval request in the same turn, and returns `pending`. Our checker counts those
  reads as the turn's tools and reports a miss. We leave it visible (README, "Deliberate
  deviation"). It is the only miss in the final run (`runs/m10-final-33-e.txt`, 32/33).
- **Judges vs checks:** the three Langfuse judges run on Nova 2 Lite and are noisy. Their notes
  on the final run are in `runs/m10-final-e-scores.txt`. Where a judge reason was right, it led to
  a fix (#39). Where it was wrong (e.g. M-S-01 t7 says record E001 is absent although turn 1
  returned it), we left it.
- **Packaging:** built and unit-tested, but the containers have not been run on the build machine
  (company laptop; Docker Desktop is waiting for IT approval).
