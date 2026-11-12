# ADR 0009 — Renewal: a persisted state machine, not a conversation

Date: 2026-11-12 · Status: accepted

## Context
Spec 11: a schedule starts the renewal workflow. It stops for people, inbound events restart it, and
the schedule wakes it again on the effective date. It must survive the process dying between any two
steps. "Persisted records, not in-memory messages, are the test oracle." The provider email is
untrusted text that gates a database write.

## Decision
- **One standalone module, `novaops/renewal.py`.** It imports `config`, `db` and `llm`, never the
  agent.
- **Every entry point is a plain function over persisted state:**
  - `scheduled_run(as_of)`;
  - `ingest_event(event)`;
  - `ingest_provider_reply(eml)`.

  A stage column (`awaiting_internal_decision` → `awaiting_clearances` → `awaiting_provider_reply`
  → `confirmed_awaiting_effective_date` → `applied`, or `needs_human`) is the "pause". Because no
  state lives in memory, killing the process between calls loses nothing, and a separate CLI process
  per step demonstrates that. We chose this over a LangGraph graph with a checkpointer: the spec
  makes the tables the oracle, and a table-driven stage is the smaller design that satisfies it.
- **Own tables in the operational SQLite file:** `renewal_cases`, `renewal_runs`, `renewal_events`
  (idempotency by `event_id`), `renewal_outbox` (idempotency by message key, delivery status incl.
  `uncertain`), `renewal_replies` (by Message-ID), and `renewal_agreements`. The recorded agreement
  is kept apart from the terms in effect. `db.reseed()` now starts from a fresh file so these
  reset with the seed.
- **What the model does, and what code does:**
  - The model does two jobs: the per-case recommendation and the reply extraction, both as
    forced-tool proposals.
  - Code does the rest: the window, notice deadline and urgency; escalation when owners conflict
    (contract document vs database, per the cleanup memo) or terms are ambiguous; the proposed
    seat count; the three preconditions; matching a reply against the APPROVED scope (decision,
    conditions, missing fields, contract, seats, price ceiling, term, run id); and every write.
- **A confirmation is recorded, not applied.** The scheduled run on or after its term start
  applies it once: seat limit, cost, term, and an audit event. Active seats are not reset. That run
  also notifies the requesters of blocked access requests for that system, with no price and no
  access grant.
- **The two ports have mocks as the required implementation.** `NotificationAdapter` uses the
  configured channel `slack`. `ProviderEmailAdapter` serves a fixture by id or seed, and can model
  an unconfirmed delivery (`uncertain`).

## Consequences
- **`tests/test_renewal.py` covers, without Bedrock:**
  - the 07-01 assessment (C001 urgent and overdue, C020 owner conflict and C017 ambiguous
    escalated);
  - no supplier contact before all three preconditions;
  - a rejection;
  - recorded on 07-03 with the seat limit still 40, then applied on 07-21;
  - every input replayed twice, giving exactly one update and one notification;
  - the four replies that must not be written;
  - a reply paired with the wrong run;
  - `uncertain` delivery;
  - independence from the agent.
- **The submission run (`evals/run_submission.py --optional`) drives each R-I input as ONE trace:**
  schedule, then three events, then the reply, then the effective-date schedule.
- **Not done:** real Slack, email or WhatsApp adapters. They are optional; the mocks are the
  required implementation.
