# ADR 0006 — Webex: a model-free approval workflow on its own thread

Date: 2026-11-10 · Status: accepted

## Context
- **Spec 9 / Milestone 4:** look up the employee, the subscription and existing tickets; find the
  real blocker (42 of 40 Webex seats); reuse `T001`/`AR001`; file an approval request, **persist it
  and stop**; release `create_access_request` only against a recorded approval; return an
  `AccessDecision` that never claims a grant. Done when a replay creates no second row and a
  killed process resumes a pending approval.
- **Spec 6.3 / 6.4:** at least one required capability has no tool in any lesson.
- The conversation must go on while an approval is pending (S2 continues after turn 10; S8 is one
  thread), so the conversational graph itself cannot sit paused in `interrupt()`.
- Checked, not assumed: re-invoking an interrupted LangGraph thread with new input restarts it from
  START (probe script, LangGraph 1.2). A replay of the same request is therefore safe as long as
  every step is idempotent.

## Decision
- **Two graphs, one SQLite checkpointer file.** The conversational graph ends a request turn with a
  typed `AccessRequestIntent` (the Maya → Webex handoff, ADR 0005). `run.py` then starts the
  **approval workflow** (`novaops/agent/approval.py`) on its own thread,
  `approval-<employee>-<system>`, inside the same trace.
- **The approval workflow contains no model call:** `gather → wait → release → decide`.
  - `gather` reads the records through MCP tools, reuses an open request (AR001) and the approval
    already waiting on it (AP001, IT Manager E006), or files one (`request_approval`, idempotent).
  - `wait` calls `interrupt()`. On resume it **re-reads the approval row**; the resume payload is
    ignored. A resume without a recorded decision pauses again.
  - `release` asks `write_gate.released_writes(approval_row)`; only `approved` releases
    `create_access_request`.
  - `decide`: `build_decision()` renders the `AccessDecision` from records. `decision_answer()`
    asserts the text never claims a grant.
- **Every write is idempotent by a natural key and audited.** Approval = (request, type, approver,
  open); access request = (employee, system, open). The server refuses `create_access_request`
  unless the named approval is recorded as approved — a second lock behind the gate.
  Timestamps use the pinned clock, so a replay writes identical rows.
- **The human channel is `python -m novaops.approve <AP> --by <id> --approve|--reject`.** It is
  application code, not a tool any model sees. Only the approver named on the row may decide, and a
  closed decision cannot be flipped. It resumes the paused thread from a fresh process and reports
  into the original trace (`trace_context`), so the pause and the resume stay one trace (spec 13).
- **The missing capability: seat assignments are not recorded.** `check_team_system_access` (for a
  manager's team) says so explicitly and reports what *is* recorded per person: role entitlement,
  access requests, onboarding tasks. W-I-02's honest answer is then grounded in a tool result,
  not in the model's restraint.
- **Tool classes:**
  - **read:** visible by loadout.
  - **write:** `create_access_request`, released only by the gate.
  - **app:** `request_approval`, `get_approval`. Called only by the workflow; excluded from every
    model's tool list (`policy.APP_TOOLS`).

## Consequences
- **Rachel (W-I-03) ends `pending`:** AP001 is waiting on E006, and T001 and AR001 are reused, so
  no row is created. After E006 approves, the workflow resumes, releases the write, and reuses
  AR001. It then ends `blocked`, because approval does not create a seat. Expansion still needs
  Finance (AP002, E011).
- **A not-entitled subject files nothing:** the result is `needs_human`.
- **Tests without AWS** (`tests/test_webex.py`):
  - pause;
  - replay;
  - "approved" said without a record;
  - resume in a new process after approval;
  - rejection;
  - not entitled;
  - only the named approver may decide;
  - writes and app tools are never in a model's loadout.
- **Not done:** no ticket is ever created. The workflows only reuse existing tickets, so
  `create_ticket` is not built (YAGNI).
