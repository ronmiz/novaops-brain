---
name: measure
description: Measure the agent before and after a change — golden replay as a mean of 3 runs, judge scores read back from Langfuse, and the result recorded. Use whenever an agent change (prompt, loadout, graph, tool) is about to be accepted.
---

# Measure a change

Nova 2 Lite varies by about ±2 turns run to run, so one run is not a measurement.

1. Run `python -m pytest -q` first. It must stay green, and it needs no AWS.
2. With the MCP server running (`python server/server.py`), run three times:
   `python evals/golden_replay.py > runs/<tag>-a.txt`, then `-b`, then `-c`.
   Add `--session S6 --session S8` (or S3, S4) when the change touches Webex or memory.
3. Wait about 2 minutes for the Langfuse judges. Then, for each results file named on the
   last line of the run output, run
   `python scripts/show_scores.py evals/results/<that file>.json > runs/<tag>-scores.txt`.
4. Report the mean pass count and the turns that pass in every run vs. only some runs.
   Note any turn where a judge and `golden_pass` disagree, and decide which is right.
5. Accept the change only if the mean moved. Record it with the `log-obstacle` skill
   (before and after numbers, root cause, fix, evidence file).

Never edit a test or a golden expectation to make a number move (`.claude/hooks/protect_tests.py`
blocks weakening tests).
