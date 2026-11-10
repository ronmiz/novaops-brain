"""Retrieval measurement — baseline first, then compare cut configurations.

Two checks, straight from GOLDEN-DATASETS.json:
  1. Recall: for each `retrieval_expectations` case, how many expected documents appear
     among the k-NN candidates, and in the final hits under each cut configuration.
     k-NN and the Nova rerank run ONCE per query; every configuration cuts the SAME
     ranked list, so the comparison isolates the cut and costs no extra model calls.
  2. Permission boundary: the S9 promotion question asked by a non-manager (Maya Cohen,
     E001) must return NO manager_playbook chunk; asked by a manager (Yael, E018) it may.

    python evals/retrieval_eval.py            # writes evals/results/retrieval-<timestamp>.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novaops import config  # noqa: E402
from novaops.rag import retrieval  # noqa: E402

GOLDEN = config.DATASET_DIR.parent / "GOLDEN-DATASETS.json"
CALLER = "E010"   # a regular employee: everything except manager_playbook is visible

CONFIGS = {
    "A baseline  >=0.6 max5":         dict(min_score=0.6, max_results=5, per_doc=None),
    "B diverse   >=0.6 max5 1/doc":   dict(min_score=0.6, max_results=5, per_doc=1),
    "C wider     >=0.5 max8 2/doc":   dict(min_score=0.5, max_results=8, per_doc=2),
}


def recall_cases() -> list[dict]:
    rows = []
    for case in json.loads(GOLDEN.read_text(encoding="utf-8"))["retrieval_expectations"]:
        expected = set(case["expected_documents"])
        candidates = retrieval.knn(case["query"], CALLER)
        ranked = retrieval.rerank(case["query"], candidates)
        row = {"case": case["case_id"], "query": case["query"], "expected": len(expected),
               "in_candidates": len(expected & {c["source"] for c in candidates}),
               "ranked": [f"{s:.2f} {c['source']} § {c['section']}" for c, s in ranked],
               "configs": {}}
        for name, params in CONFIGS.items():
            hits = retrieval.cut(ranked, **params)
            found = expected & {h["source"] for h in hits}
            row["configs"][name] = {"found": len(found), "hits": len(hits),
                                    "missing": sorted(expected - found)}
        rows.append(row)
    return rows


def permission_cases() -> list[dict]:
    question = "How do I get promoted here? What does the path look like for a CSM?"
    rows = []
    for caller, may_see in [("E001", False), ("E018", True)]:
        sources = {c["source"] for c in retrieval.knn(question, caller)}
        leaked = sorted(s for s in sources if s.startswith("documents/manager_playbook/"))
        rows.append({"caller": caller, "manager": may_see,
                     "manager_playbook_chunks": len(leaked), "ok": may_see or not leaked})
    return rows


def main() -> None:
    recall, perms = recall_cases(), permission_cases()
    total = sum(r["expected"] for r in recall)
    print(f"k-NN candidates (top {retrieval.CANDIDATES}): "
          f"{sum(r['in_candidates'] for r in recall)}/{total} expected documents\n")
    print(f"{'configuration':<32}{'found':>8}{'avg hits':>10}   per case")
    for name in CONFIGS:
        found = sum(r["configs"][name]["found"] for r in recall)
        avg_hits = sum(r["configs"][name]["hits"] for r in recall) / len(recall)
        per_case = " ".join(f"{r['configs'][name]['found']}/{r['expected']}" for r in recall)
        print(f"{name:<32}{found:>5}/{total:<3}{avg_hits:>8.1f}   {per_case}")
    print("\nStill missing under C:")
    for r in recall:
        missing = r["configs"][list(CONFIGS)[-1]]["missing"]
        print(f"  {r['case']:<16}{', '.join(m.split('/')[-1] for m in missing) or '-'}")

    print("\nPermission boundary (S9 turn 1):")
    for p in perms:
        print(f"  {p['caller']} manager={p['manager']}: {p['manager_playbook_chunks']} "
              f"manager_playbook chunks -> {'OK' if p['ok'] else 'LEAK'}")

    out = Path(__file__).parent / "results" / f"retrieval-{datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"recall": recall, "permissions": perms}, indent=2), encoding="utf-8")
    print(f"\nSaved {out.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
