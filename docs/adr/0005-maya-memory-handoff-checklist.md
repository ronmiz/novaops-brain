# ADR 0005 — Maya: distilled memory, typed handoff, validated checklist

Date: 2026-11-10 · Status: accepted

## Context
The Maya sessions are long and messy.
- **S2 (12 turns):** a constraint from turn 1 (the Q3 SaaS freeze) is needed on turn 9. A tangent
  on turn 4 must stop steering tool choice. Turns 7, 10 and 12 need no tool.
- **Turn 10:** asks Maya to "go ahead and file". Maya never writes (spec 8).
- **Spec 6.5:** requires an `OnboardingChecklist` (items with status and at least one citation,
  blocked items with a reason, an overall status) and a typed Maya → Webex handoff.

## Decision
- **Memory (Lesson 10 stage 3):**
  - A `distil` node folds history into five *named* fields once fresh history passes 12 messages
    or about 10k characters.
  - The planner reads memory plus only the messages after it.
  - A memory that drops an active constraint is rejected, and the raw history is kept
    (`memory.memory_is_safe`).
- **Handoff instead of a write:**
  - When the planner flags `action_requested` and the write gate released nothing, the graph
    goes to `handoff`, not `answer`.
  - The model only *proposes* who, what system and why (`AccessRequestProposal`).
  - Application code adds `requested_by`, `source_thread_id` and `request_id`, giving an
    `AccessRequestIntent` with `status=pending_approval`.
  - The reply text is a fixed template. It never claims a filing or a grant.
  - The turn's `status` is `pending`.
- **Checklist:** after an onboarding turn that used tools, a `checklist` node extracts an
  `OnboardingChecklist` from the tool evidence. `contracts.checklist_errors` validates it
  deterministically:
  - every item needs a citation;
  - every citation must appear in a tool result;
  - a blocked item needs a reason.

  There is one bounded retry with the errors fed back. If it is still invalid, the status is
  `needs_human`, with the errors attached.
- **Citations:** `contracts.citation_report` flags any cited document or record that no tool
  returned. Invented citations were the Milestone 2 failure (OBSTACLES #5).
- **Restricted content:** the answer prompt says the manager playbook is for managers only.
  The *enforcement* stays at retrieval (ADR 0002). The prompt only makes the refusal honest.

## Consequences
`evals/golden_replay.py` replays S1/S2/S9 on one thread per session against a reseeded database
and scores every binding golden field, plus our own citation, constraint-carry and no-write
checks. Milestone 4 consumes `AccessRequestIntent`: it persists an approval request, pauses, and
releases the write only against a recorded approval.
