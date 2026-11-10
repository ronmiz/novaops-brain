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
| `M-I-01` | — | `a5be6972edf47d3b6d589ea5702e4c9b` |
| `M-I-02` | — | `391c7f4cfc26137d9381489035c75b83` |
| `M-I-03` | — | `9ff157a7c57afa26fbdd46410b4dfe50` |
| `M-S-01` | 1 | `eafe7e58fecd475f4f32b5de7e81acb5` |
| `M-S-01` | 2 | `a316e493a50eb895c75487e4ad5c9cab` |
| `M-S-01` | 3 | `e41d686e1008477da6a5a006f6949053` |
| `M-S-01` | 4 | `cbb8c027eca437fd385309788e325c06` |
| `M-S-01` | 5 | `6bcee64a03ab79cb8d03bb55a936d1d1` |
| `M-S-01` | 6 | `e223a6bd8498290670782610d831cdd8` |
| `M-S-01` | 7 | `eaf2994777d36ea4766ebbb20aa88c4b` |
| `M-S-01` | 8 | `607d15ef5fc7c084eeb06df32ddbcff3` |
| `M-S-01` | 9 | `66356293d4e10d8653d0d86574b70a29` |
| `M-S-01` | 10 | `60e9f34275144094ccdf119377cf6e92` |
| `M-S-01` | 11 | `fed2eaead41284e69c1d08299f4b4f9e` |
| `M-S-01` | 12 | `6e1ab9e71f264454738accebb3c6c72d` |
| `M-S-02` | 1 | `a85176e5be6aa27e7d1fac6f3911f4e5` |
| `M-S-02` | 2 | `b2ba7a49975a0ee14a2df789b43f2219` |
| `M-S-02` | 3 | `25d22e759ac572600a58f902bb998fbc` |
| `M-S-02` | 4 | `c40ad65f59f5d2f0914ff1dbfeaf6599` |
| `M-S-02` | 5 | `9c9ae9e72ed6acd5cbfe2c0106365ad9` |

### Webex - IT operations

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `W-I-01` | — | `25e5d7ef50785aa84d0f2b8f6dbb17e2` |
| `W-I-02` | — | `896ac032ec42da65bd739f8346f38f6f` |
| `W-I-03` | — | `053f2f72187f5900ae72b731220bfc9d` |
| `W-S-01` | 1 | `165673723877c626e3fc18b6ddec38d2` |
| `W-S-01` | 2 | `ce4491d86522d61f7b94ff8507f38694` |
| `W-S-01` | 3 | `5f2b853a264c20b3196128eb057a36b9` |
| `W-S-01` | 4 | `b7a7d792eaef3ac0ec3d78bb2f2442d3` |

### Vendor - CRM extraction  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `V-I-01` | — | |
| `V-I-02` | — | |
| `V-I-03` | — | |

### Renewal - contract renewal  *(optional)*

| Item | Turn | Trace ID |
| ---- | ---- | -------- |
| `R-I-01` | — | |
| `R-I-02` | — | |
| `R-I-03` | — | |

---

## 6. Anything I should know

Two or three sentences, optional. Known gaps, a deliberate deviation and why, something you
would do differently. Honesty here costs nothing and helps — a stated limitation reads better
than one discovered while marking.

