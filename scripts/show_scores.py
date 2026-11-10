"""Read back every score on the turns of one replay — the LLM judges beside our checks.

    python scripts/show_scores.py evals/results/golden-S1-20261110-2019.json
    python scripts/show_scores.py evals/results/submission-all-20261111-0930.json

One line per turn: golden_pass (ours) and the three judges, then each judge's reasoning when
it scored below 1.0 and the failed checks when golden_pass is 0 — so a disagreement between a
judge and a check is visible at a glance. Judges run on Langfuse a minute or so after a turn;
a turn whose judge column is '-' has not been judged yet. Uses the v3 scores API.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novaops import config  # noqa: E402,F401  (loads the shared .env)
from langfuse import get_client  # noqa: E402

NAMES = ("golden_pass", "expected_pass", "faithfulness", "citation_quality", "no_overclaim")


def scores_for(api, trace_id: str) -> dict:
    out, cursor = {}, None
    while True:
        page = api.scores_v3.get_many_v3(trace_id=trace_id, fields="details", limit=100, cursor=cursor)
        for s in page.data:
            out[s.name] = (getattr(s, "value", None), s.comment)
        cursor = page.meta.cursor if page.meta else None
        if not cursor or not page.data:
            return out


def main(results_path: str) -> None:
    api = get_client().api
    rows = json.loads(Path(results_path).read_text(encoding="utf-8"))
    print(f"{'turn':<12}" + "".join(f"{n:>18}" for n in NAMES))
    for r in rows:
        got = scores_for(api, r["trace_id"]) if r.get("trace_id") else {}
        cells = [f"{got[n][0]:.1f}" if n in got and isinstance(got[n][0], (int, float)) else "-" for n in NAMES]
        label = r.get("item") or r["session"][:3]          # submission rows / golden rows
        print(f"{label + ' t' + str(r['turn'] or '-'):<12}" + "".join(f"{c:>18}" for c in cells))
        for n in NAMES:
            value, comment = got.get(n, (None, None))
            if isinstance(value, (int, float)) and value < 1.0 and comment:
                print(f"    {n}: {comment[:300]}")


if __name__ == "__main__":
    main(sys.argv[1])
