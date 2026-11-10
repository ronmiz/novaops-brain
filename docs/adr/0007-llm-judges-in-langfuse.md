# ADR 0007 — LLM judges registered in Langfuse; deterministic scores from our checks

Date: 2026-11-10 · Status: accepted

## Context
- **Spec 14:** score runs with deterministic checks first, then **register** LLM judges for
  what code cannot check (citation quality, whether the answer claims access was granted).
- **Spec 3:** the work is assessed by reading the repository and the Langfuse traces, not by
  running anything.
- **Lesson 11 (Yitar):** Maya is judged on faithfulness; Webex on tool use and never claiming
  a grant.
- **Two options:**
  - Our own judge script that calls Nova through `llm.py` and posts scores.
  - Langfuse-hosted evaluators, which is the Lesson 11 exercise 4 method.

## Decision
- **Langfuse-hosted evaluators, registered by a script in the repo** (`evals/register_judges.py`).
  - The judges then run on every turn of the submission set without us, and a reviewer sees each
    score and its reasoning on the trace.
  - The rubrics stay reviewable in git.
  - They run on the project's own LLM connection: provider `Bedrock-Nova-Lite-2`, model
    `us.amazon.nova-2-lite-v1:0`.
- **Three judges:**
  - `faithfulness`: the proportion of claims supported by the evidence.
  - `citation_quality`: the proportion of claims carrying a citation that supports them. Code
    already checks that a citation exists in the tool output; only a reader can check that it
    supports the sentence.
  - `no_overclaim`: no "granted", "filed" or "done" that the evidence does not show.
- **One judgement per turn.**
  - Each turn's root span has the fixed name `novaops-turn` (`run.TURN_SPAN`). The rules filter
    on `type = AGENT` and that name, because LangGraph's `agent-turn` run and the approval
    resume are AGENT observations too.
  - Caller and thread remain the trace's user and session.
- **The judge's evidence is copied onto the span.** A rule reads only that one observation, so
  `run.trajectory()` writes `calls` (this turn's tool results, truncated) and `state` (user rules,
  memory, earlier tool results). The rules pull them with `jsonPath`.
- **Deterministic scores are written beside the judges.** `evals/golden_replay.py` posts
  `golden_pass` with the failed checks as the comment, so a judge and a check that disagree are
  visible on the same trace.

## Consequences
- **Rules only judge observations created after they exist.** Register the judges before the
  submission run.
- **The AWS keys for Bedrock live in our Langfuse project.** This is the trade Lesson 11 asks for
  knowingly: a judge that runs without us has to hold its own keys.
- **Readers:** the legacy trace API is closed to our organisation (OBSTACLES #21), so anything
  that reads runs back uses `GET /api/public/v2/observations`.
