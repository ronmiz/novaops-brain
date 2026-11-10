---
name: log-obstacle
description: Record an obstacle (error, wrong assumption, environment trap, measured defect) as the next numbered row of docs/OBSTACLES.md. Use after any failure is understood and fixed.
---

# Log an obstacle

Append ONE row to `docs/OBSTACLES.md`, numbered after the last row:

`| N | YYYY-MM-DD | <milestone> | <symptom, with the measured numbers> | <root cause> | <fix> | <evidence: run file, results json, test name> |`

- **Symptom:** what was observed, verbatim where possible (error text, score, answer
  excerpt).
- **Root cause:** why it happened. If the first explanation turned out wrong, say so; the
  record is more useful than looking right.
- **Fix:** the change, and where it is (function or file).
- **Evidence:** the `runs/…` or `evals/results/…` file, plus the test that now guards it.

A non-obvious design decision also gets a new ADR in `docs/adr/`. Never edit an old ADR.
