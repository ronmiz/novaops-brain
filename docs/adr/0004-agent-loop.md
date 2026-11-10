# ADR 0004 — One agent loop; visibility and authorization kept apart

Date: 2026-11-10 · Status: accepted

## Context
Spec section 2: `message → classify → scope → gather evidence → answer`, plus a write gate that
releases an action only against a recorded approval. Maya and Webex are two scopes on one graph.
Two rules from spec 6.6:
- Caller identity is an application input, never something the model infers.
- There is a single path into the workflow.

## Decision
- **Graph:** Lesson 10's stage-2 shape (`novaops/agent/graph.py`):
  `classify` (planner model call returns a TurnPlan) → `scope` (plain code: intent → visible
  read tools, and intent → scope maya/webex) → `model` ↔ `tools`, with a one-time `rearm`
  fallback. The classify step *is* the router; there is no separate router above it.
- **Visibility vs authorization:**
  - `policy.LOADOUTS` decides what the model *sees* and contains no write tool.
  - `write_gate.released_writes(approval)` is the only function that can add a write tool. Its
    only input is an approval record, so message text can never open it. In Milestone 2 it
    releases nothing.
- **Caller identity:**
  - `caller_id` is removed from the schema the model sees (`graph.model_schema`).
  - The tools node fills it from state and overrides anything the model sends.
  - A call to a tool that was not visible this turn is refused.
- **Durable state:** a per-thread SQLite checkpointer (`var/checkpoints.db`).
- **One entry point:** `novaops/agent/run.py::ask()`. The CLI, tests, eval runner and UI all
  call it.

## Consequences
The properties are checked without AWS in `tests/test_agent_loop.py`. Milestone 3 adds history
distillation for the 12-turn session. Milestone 4 adds write tools and passes the recorded
approval to the gate.
