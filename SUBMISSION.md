# NovaOps final project — submission

Fill this in and commit it to your repository as `SUBMISSION.md`. It is the first thing read,
and it is how every trace gets found.

---

## 1. Repository

| | |
| ------------------- | ------------------------------------------------ |
| **Repository URL**  | `https://github.com/<you>/<repo>` |
| **Access**          | public / instructor added as collaborator *(delete one)* |
| **Commit reviewed** | `<full sha>` |

## 2. Langfuse

| | |
| ------------------ | --------------------------------------------- |
| **Host region**    | `cloud.langfuse.com` EU / US *(delete one)* |
| **Project name**   | |
| **Instructor role**| Member *(required — traces are read through the API)* |
| **Invitation accepted** | yes / no |

## 3. Scope completed

| Workflow | Built | Notes |
| --------------------------- | ------ | ----- |
| 1 — Maya · HR and onboarding | required | |
| 2 — Webex · IT operations    | required | |
| 3 — Vendor · CRM extraction  | optional, +5 | |
| 4 — Renewal · contract renewal | optional, +10 | |

| Optional stage | Done | Evidence |
| ------------------------------- | -------- | -------- |
| Lesson 12 — loop engineering     | yes / no | |
| Lesson 14 — packaging and deploy | optional, +5 | |

## 4. Durable-behavior evidence

Some required behavior cannot be seen in a single trace. Point at the commit, test, or trace
that proves each — one line, or "not attempted".

| Check | Evidence |
| ------------------------------------------------------------- | -------- |
| Replaying a request creates no second ticket or access request | |
| A pending approval survives the process being killed and restarted | |
| The write gate releases only against a recorded approval | |
| *Renewal (optional): every event replayed twice leaves one update and one notification per recipient* | |

## 5. Trace index

One row per item in `EVALUATION-INPUTS.yaml` — 27 required, 33 with both optional workflows.
**Fill in the trace id column only**; the ids and turn numbers are already correct. Leave a row
blank if you did not run it.


### Maya - HR and onboarding

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `M-I-01` | — | `7d362fffa627c07ce9a29e58ba6068e2` |
| `M-I-02` | — | `60084d3e6d0a0cd1f255d048a5600c39` |
| `M-I-03` | — | `2fb62bb97cde1ceccdf5208377760de5` |
| `M-S-01` | 1 | `6b4d2649c04fce7217e32070935799f7` |
| `M-S-01` | 2 | `3529d0f7e88594841014551108b20233` |
| `M-S-01` | 3 | `81a912c7917325849c7c4d930331ce1d` |
| `M-S-01` | 4 | `e0fd6697f52a54ca86f015cdb56c551f` |
| `M-S-01` | 5 | `60ad08452c015da27008d14346d980db` |
| `M-S-01` | 6 | `b283af0a7d9f516d3af1049e8b432986` |
| `M-S-01` | 7 | `801b0d1eb6f7368f7ffd322325c62053` |
| `M-S-01` | 8 | `cd62e828553fd10c2ed8fc048a05b144` |
| `M-S-01` | 9 | `2e4b9a48f409e8fee659c008ad555503` |
| `M-S-01` | 10 | `42b1eae106567c7a7b5e5b2e1a3313b1` |
| `M-S-01` | 11 | `74b1bba9a5278f8906ee7ef481073132` |
| `M-S-01` | 12 | `cd4f801b1d12bd54f28ea400713519d0` |
| `M-S-02` | 1 | `d90278e7cb2be39ad79a098e1f2b51a1` |
| `M-S-02` | 2 | `dd32ff31dcf0f6adee2544e3b2b8f002` |
| `M-S-02` | 3 | `0fb2d38ccaf5719c41bd8e4f8e344fc0` |
| `M-S-02` | 4 | `9edfd4105033c0a546c5a51fb001c28d` |
| `M-S-02` | 5 | `9b076cd423f3f7e4ad7edfaffebcf4e9` |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | `2d6b646ffb00ee419b0ad055e9bbed42` |
| `W-I-02` | — | `d7b5a2eebb778f3b682dc158e714f532` |
| `W-I-03` | — | `79d1258049eb07ed8759ae03dd6769f1` |
| `W-S-01` | 1 | `61307a9a165ea5579a3285893e7426d7` |
| `W-S-01` | 2 | `3b02b0056e51eac16669f91fcd1ddadd` |
| `W-S-01` | 3 | `99ebc3a089f7fc1c2b8b65c0a8a80cd1` |
| `W-S-01` | 4 | `2154572ce7f8944277188fc15e77735b` |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | `1272a2e64c1380d34cb98d1f870199c6` |
| `V-I-02` | — | `9941f6ee5d5d7728311330d7874005ee` |
| `V-I-03` | — | `9c522e09f57f5b00282f70ad8f2692d8` |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | `f5fa036625e47fc9e394edd22bab5a16` |
| `R-I-02` | — | `57862133642328a7f350dc66e7146145` |
| `R-I-03` | — | `21db8b0297ffffe5e6c0570cb9e59b0d` |

---

## 6. Anything I should know

Two or three sentences, optional. Known gaps, a deliberate deviation and why, something you
would do differently. Honesty here costs nothing and helps — a stated limitation reads better
than one discovered while marking.

