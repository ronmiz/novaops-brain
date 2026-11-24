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
| `M-I-01` | — | `32a678061ef748e2f80e484e78bc37cc` |
| `M-I-02` | — | `ecd198c16486271cd88f7e1d65489da0` |
| `M-I-03` | — | `1ab2fad94c274308d3ffee90defaea98` |
| `M-S-01` | 1 | `2b7be5754314bd53fc61842c167ec7a4` |
| `M-S-01` | 2 | `a4d663a7f1cd6e01fd39d348909d4082` |
| `M-S-01` | 3 | `a4cc05c7e4600d2c8d9cbe1c1da64f69` |
| `M-S-01` | 4 | `9be10606c892b10d13c44ed1f9773fe0` |
| `M-S-01` | 5 | `e3d4fd2c7b5fbf3895b1fdde03d7ed44` |
| `M-S-01` | 6 | `dd8e23ff45a354a45c64553cfd0ccb8e` |
| `M-S-01` | 7 | `ff4ffd0040562225d9f8dd7f909d8039` |
| `M-S-01` | 8 | `ff36e68ec9a7064a0bf78bec118d317f` |
| `M-S-01` | 9 | `e1e6b6f3f10a40594fb6f16abf5cf337` |
| `M-S-01` | 10 | `5ce15e799a7a4583fa47565cffeeb3f1` |
| `M-S-01` | 11 | `5213f3cae3253e34f6fadba33b69e594` |
| `M-S-01` | 12 | `d02b7533ea0c4f00faaf1a1883126609` |
| `M-S-02` | 1 | `bc4f4046d2f32c9de8af3e8358566d51` |
| `M-S-02` | 2 | `d50455fef98d4c389eaf3c67e2613c59` |
| `M-S-02` | 3 | `cc74ca63c918c1cecbb2fb01d3ac4515` |
| `M-S-02` | 4 | `444d7d5b8a51efc77e77132221b8f91a` |
| `M-S-02` | 5 | `0aeabb49bbabc491bc4ba14378f4d22a` |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | `2f66b9538c4e505ac2bb906dc026ff42` |
| `W-I-02` | — | `200ca8fb4158bb255b5f024450be4a71` |
| `W-I-03` | — | `a8a452a9bb8fea989e229ad01376c423` |
| `W-S-01` | 1 | `efb44fe7f30db8ffd5d5fdf6f152ad93` |
| `W-S-01` | 2 | `566053d00f2bc4ee532a7a798bd5eca1` |
| `W-S-01` | 3 | `b8f50a8f048895a5014e580f806c85ba` |
| `W-S-01` | 4 | `1564b1ec32f0e863bb1d881a2e6472e7` |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | `41472ed48e1df63c4607e063374ce346` |
| `V-I-02` | — | `a9f34be5e337d3104e984b49c59d58f4` |
| `V-I-03` | — | `afd25e13887d7fd3a7cc1e4274e992c4` |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | `59f07d2e76455f4beb64cee8f7fbc7f0` |
| `R-I-02` | — | `acf3940267884ba9a03c8fa6f15377c3` |
| `R-I-03` | — | `fb15d8f967de868f499252d71fd46724` |

---

## 6. Anything I should know

Two or three sentences, optional. Known gaps, a deliberate deviation and why, something you
would do differently. Honesty here costs nothing and helps — a stated limitation reads better
than one discovered while marking.

