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
| `M-I-01` | — | `e2cbc108b3ea1e67d363d271787f49e7` |
| `M-I-02` | — | `53ed504af69eb2e7a485649a7e14866f` |
| `M-I-03` | — | `7acc1fc8e8e8131e78b7dfcbdcd4e6e5` |
| `M-S-01` | 1 | `4ad4976b26df00c246366a8954f379c2` |
| `M-S-01` | 2 | `ba46299aaa6929dadfbf9dec26873871` |
| `M-S-01` | 3 | `4d537bc962c03460b83906dd74944336` |
| `M-S-01` | 4 | `4df2182a6c11205761fb5ad105866ba4` |
| `M-S-01` | 5 | `812e0c53fbbb1798a59bf649c09e8c02` |
| `M-S-01` | 6 | `8ad00176542ff0fc9cd8c551e5604b79` |
| `M-S-01` | 7 | `e86acecde7a9b45373897543661baa38` |
| `M-S-01` | 8 | `72eb2356b4ed1994ec1f97a7d1fc23b4` |
| `M-S-01` | 9 | `eb88318d573628daa0a8aa839802b366` |
| `M-S-01` | 10 | `f813a6fdd02527d89c61eff9b8b30686` |
| `M-S-01` | 11 | `697d94e3b2852f210d0aeb5656bbf64f` |
| `M-S-01` | 12 | `cebc08615737584ccd85e8ea229c130e` |
| `M-S-02` | 1 | `8670d63ac1c4be50b573e43ee328b219` |
| `M-S-02` | 2 | `1150a3adb0a846e1bc2db41d5e8834e2` |
| `M-S-02` | 3 | `77b2fe256d2b4b790af51e31193f51ef` |
| `M-S-02` | 4 | `870c6e7dc707733ac692385bcd7c10d3` |
| `M-S-02` | 5 | `05aa6dd024e32742420e547d9d6aed42` |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | `89f07faba3eee2e0fbc15a9536b1e7e9` |
| `W-I-02` | — | `c0efc10b29fe35df979f6f25e4d18efe` |
| `W-I-03` | — | `a60b4936f0cbee003f4c5e6ef8d4f426` |
| `W-S-01` | 1 | `2fe0aa49e37d2b1e4707246ab2a8a0bb` |
| `W-S-01` | 2 | `e9fecaa4a4417929a4c4b90a0e0357e6` |
| `W-S-01` | 3 | `6792be2bed193de86e5985da1c7cfddc` |
| `W-S-01` | 4 | `c73628d295439419f320499b85ab97f4` |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | `0fb31c0c942af95e19c477bca42ba5e5` |
| `V-I-02` | — | `3b66566c0ba02f307966889a3c014a70` |
| `V-I-03` | — | `310da773e9b5635d7f06a40809f53753` |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | `16823fb5cd99061981acc56e9fe57bac` |
| `R-I-02` | — | `7f4459b07dfc1cc0bbe50f3d4f9c7797` |
| `R-I-03` | — | `4a5358634eaead5ed44aecc79452fcce` |

---

## 6. Anything I should know

Two or three sentences, optional. Known gaps, a deliberate deviation and why, something you
would do differently. Honesty here costs nothing and helps — a stated limitation reads better
than one discovered while marking.

