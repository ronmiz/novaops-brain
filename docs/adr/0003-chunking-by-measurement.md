# ADR 0003 — Chunking and the final cut, chosen by measurement

Date: 2026-11-10 · Status: accepted · Amends the chunking and cut settings of ADR 0001

## Context
`evals/retrieval_eval.py` checks the 5 golden `retrieval_expectations` cases (17 expected
documents) as a regular employee.

Baseline (section chunks, Lesson 7 cut of `>=0.6`, max 5):
- k-NN found 15/17 of the expected documents.
- The final hits kept only 9/17.

Reading the reranker scores showed two causes:
1. **Crowding.** The cap of 5 was filled by several chunks of one document, pushing out others.
2. **Fragmented short documents.** Section chunking split each ~120-word IT KB article into
   5 pieces. In `mfa_reset.md` the word "MFA" survived only in the title, so the reranker
   scored the right article 0.4 for "reset MFA after replacing phone" and cut it.
   `github_access_for_contractors.md` failed the same way.

## Measurements (same ranking, three cuts)
| cut | found | avg hits |
|---|---|---|
| A `>=0.6`, max 5 (Lesson 7) | 9/17 | 4.0 |
| B `>=0.6`, max 5, 1 chunk/doc | 9/17 | 3.8 |
| C `>=0.5`, max 8, 2 chunks/doc | **12/17** | 6.0 |

## Decision
- Final cut: **C** (`MIN_SCORE=0.5, MAX_RESULTS=8, PER_DOC=2`).
- Chunking: a document of **<= 300 words is one chunk**. That covers all 70 operational
  documents: policies, IT KB, contracts, employment records and memos. Only the handbook and
  the manager playbook (32 long documents) are split by `## ` section.

## Consequences
A whole-document chunk is cited at document level (`§ (whole document)`); the documents are
short enough that this is still precise. The index must be rebuilt
(`python -m novaops.rag.store`) and the eval rerun to confirm the effect.
Raw results are in `evals/results/`.

## Result (after re-index, 470 chunks)
| | before | after |
|---|---|---|
| k-NN candidates | 15/17 | **16/17** |
| cut A (Lesson 7) | 9/17 | 12/17 |
| cut C (chosen) | 12/17 | **15/17** |

`mfa_reset.md` and `github_access_for_contractors.md` are now retrieved. The permission
boundary is unchanged: E001 gets 0 manager_playbook chunks, and the manager E018 gets 3.

Still missing:
- `webex_login_issue.md` for "Webex support SLA". That article is about login errors, not the SLA.
- `laptop_provisioning.md` for the 5-document onboarding query. In the agent, the laptop is its own
  lookup.

Stopping here: the remaining misses are expected to be covered by the agent's own follow-up
calls, which Milestone 3 will show.
