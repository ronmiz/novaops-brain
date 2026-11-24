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
| `M-I-01` | — | `754ccd91c069918b7f706b573bd97407` |
| `M-I-02` | — | `59e1f37934a9fe79d9d6bddfde822b7d` |
| `M-I-03` | — | `fd85d39ffb2fdc83d382d4a0ef1e7a6a` |
| `M-S-01` | 1 | `7f48873d0b484c9cd3b767e82dcfcc3a` |
| `M-S-01` | 2 | `8a1b11f18b803a1166643da722b3acf3` |
| `M-S-01` | 3 | `d4bb960971e6f0a35f31421be2041aed` |
| `M-S-01` | 4 | `12121cd50816412a5fc58bae698b2a06` |
| `M-S-01` | 5 | `db5c7149f4e3f6aa18639b73ed3f29b2` |
| `M-S-01` | 6 | `292e3dc2a7b363a51bdd59409953d6fb` |
| `M-S-01` | 7 | `4d8836cee618b464460b004aaade63b9` |
| `M-S-01` | 8 | `dc751c7d1c2eca767239b703f4723c75` |
| `M-S-01` | 9 | `e91d9045aff5c3b13126af307096dda7` |
| `M-S-01` | 10 | `acd5d4de63af9b66a593b925084b722c` |
| `M-S-01` | 11 | `32223c48371a52861e70e9b5ad6ab593` |
| `M-S-01` | 12 | `f8cd2c3cef4082ead0916eda891593b9` |
| `M-S-02` | 1 | `3acf85da4a45f896e57a59de77de5dcb` |
| `M-S-02` | 2 | `ce7d2144524123af1bf39a4e2718d32b` |
| `M-S-02` | 3 | `c4511d9360ef402b8fd7570e7facca92` |
| `M-S-02` | 4 | `1a0b7f6a8e669213668d0e025f1ef9cb` |
| `M-S-02` | 5 | `89bd68c04d8cc9d0673b6b2eb3911923` |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | `cff9fa31656c2410afc5c2c83e39fac1` |
| `W-I-02` | — | `c78415ccb5cf492d91eb055adc6c7dce` |
| `W-I-03` | — | `19348590d5991893b46be52b263a4cd5` |
| `W-S-01` | 1 | `79de9754731885fc5c126b762f609f03` |
| `W-S-01` | 2 | `11115f61d768b490e23d353bf6e888e6` |
| `W-S-01` | 3 | `338be452c0769049355fc901661bed1e` |
| `W-S-01` | 4 | `28c4d0fa4aad8907b7f790a70776f374` |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | `b366ce405b10d0cbffa6404b449a5b39` |
| `V-I-02` | — | `2b43e5fbda5791e57353556d6cdbd00d` |
| `V-I-03` | — | `9ca6f2dbfd03b49e6e1f67058caffb5c` |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | `87c080c27391d812bed5c62c6f2dcafe` |
| `R-I-02` | — | `5b49047a1bd2dfcf9c67740774be10ac` |
| `R-I-03` | — | `a6d0692ac07174f682aa8252a15410c4` |

---

## 6. Anything I should know

Two or three sentences, optional. Known gaps, a deliberate deviation and why, something you
would do differently. Honesty here costs nothing and helps — a stated limitation reads better
than one discovered while marking.

