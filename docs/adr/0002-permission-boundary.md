# ADR 0002 — Permission boundary at the retrieval layer

Date: 2026-11-10 · Status: accepted

## Context
`manager_playbook/` is `audience: manager`. Spec section 12: a restricted chunk that reaches the
model has already leaked, so refusing afterwards is not enough. `user_group` cannot express
"manager": Yael Romano (E018) manages three people but is `UG_REGULAR`.

## Decision
- **Who is a manager:** a caller whose id appears as some employee's `manager_id`
  (`db.is_manager`). Unknown callers are not managers.
- **Where it is enforced:** a `term audience=all` clause inside the k-NN query for
  non-managers (`retrieval.access_clauses`). Restricted chunks never leave OpenSearch.
- **Fail closed within the restricted collection only:** everything under
  `manager_playbook/` is indexed as `manager`, even without front matter. Collections with no
  `audience` field are indexed as `all`. Absent metadata means unrestricted, not deny;
  denying them would hide 70 of the 102 documents.

## Consequences
One function decides access, and the tests cover it without AWS. The agent passes the caller id
it received from the application; the model never supplies it (wired in Milestone 2).
