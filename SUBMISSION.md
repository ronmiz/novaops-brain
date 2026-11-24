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
| `M-I-01` | — | `ab812e74e9c1a4c7baa35321c5d4c43a` |
| `M-I-02` | — | `f80caadc1f9b266c4b5650c8cd79dac6` |
| `M-I-03` | — | `612d51e62d15be71017cb141da3a5f57` |
| `M-S-01` | 1 | `0935952d6df059b95c7f14d7bfefbda7` |
| `M-S-01` | 2 | `98916d577e73fe7ed978c8ed663ba438` |
| `M-S-01` | 3 | `bada7a8582604e72ae37cf9424c357a5` |
| `M-S-01` | 4 | `9371d6904469b3b63921ead06a0ca43a` |
| `M-S-01` | 5 | `9a6ee3a0bc02b7ebdc76a5cb5a8163cc` |
| `M-S-01` | 6 | `e49d56959deb05e9253b84d1c1d1be7c` |
| `M-S-01` | 7 | `4a4bb5e4cb8586e4f845d1ad94405be9` |
| `M-S-01` | 8 | `882901c79bdb604871cbe77b461d7e5e` |
| `M-S-01` | 9 | `eddd4557e670e892cc5fe42b2a9f4225` |
| `M-S-01` | 10 | `0d50257ebb7ae64e590455338da23cc7` |
| `M-S-01` | 11 | `f82b4e4c4900e06eee4a43ef19f60ffc` |
| `M-S-01` | 12 | `7aaf6bfdc28887d73e6baa4a3349fea2` |
| `M-S-02` | 1 | `d62e7291eb6677124fc5914fbdbe3f18` |
| `M-S-02` | 2 | `a97e46acf17a2aea1b4cb9aa35c5bfc0` |
| `M-S-02` | 3 | `e1f6bbb4e3851aaceb3357b147bd8917` |
| `M-S-02` | 4 | `fb8ca3e901f16cd9c10f646cabc938f5` |
| `M-S-02` | 5 | `7fdd5b31ea335bd1a3bcb53587548883` |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | `a7c00e380cd5927b959d1988d7d4fd5d` |
| `W-I-02` | — | `fa6c7c695ac149ebd4816eaa113c7f35` |
| `W-I-03` | — | `b8a14b9c149c0c421c73c01d4a570f4f` |
| `W-S-01` | 1 | `70792d0ec8a6f085c5e692c39b1c650f` |
| `W-S-01` | 2 | `5d7af47b92fc37a181b557023c95657d` |
| `W-S-01` | 3 | `d9785c3c23df95b7f00767440d0138d6` |
| `W-S-01` | 4 | `b351832ecd18a09ccb03ae0a480d7b5f` |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | `8dde15faeadb0d3c235069c0fd58df5f` |
| `V-I-02` | — | `dbc98a344214eb5a54f21f1592c49bf0` |
| `V-I-03` | — | `e751be1c7aaa8a987ef134522e49fb0f` |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | `e25806b4ac75708e26371aea00fa282a` |
| `R-I-02` | — | `1fdfd529d5913f1d7e2652c587ab7cbe` |
| `R-I-03` | — | `5cd19ffa274d503e129a5222bbd0adb0` |

---

## 6. Anything I should know

Two or three sentences, optional. Known gaps, a deliberate deviation and why, something you
would do differently. Honesty here costs nothing and helps — a stated limitation reads better
than one discovered while marking.

