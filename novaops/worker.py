"""The renewal worker — a SEPARATE entry point from the API (request plane vs event plane).

    python -m novaops.worker                       # one scheduled run at the pinned clock, then exit
    python -m novaops.worker --as-of 2026-07-21
    python -m novaops.worker --every 86400         # stay up: one run per interval (Compose)

The schedule is a plain function call (spec 11: "it does not need cron to count"); state lives
in the database, so the worker can be stopped and restarted between any two runs.
"""
import argparse
import json
import time

from . import config, renewal


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--as-of", default=config.TODAY)
    p.add_argument("--every", type=int, default=0, help="seconds between runs; 0 = run once")
    args = p.parse_args()
    while True:
        out = renewal.scheduled_run(args.as_of)
        print(json.dumps({"as_of": args.as_of, "applied": out["applied"],
                          "run_stage": (out["run"] or {}).get("stage"), "cases": len(out["cases"])}), flush=True)
        if not args.every:
            return
        time.sleep(args.every)


if __name__ == "__main__":
    main()
