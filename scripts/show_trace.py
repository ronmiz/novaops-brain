"""Read one trace back from Langfuse through the API — what a reviewer sees, as text.

    python scripts/show_trace.py <trace_id>

Prints the trace's observation tree (name, type, time) and the root spans' metadata, so a
pause and its later resume can be checked to be ONE trace (spec 13) without a browser.

Uses GET /api/public/v2/observations. The legacy GET /api/public/traces/<id> is refused for
organisations created after 2026-09-16 and removed for everyone on 2026-11-16
(docs/OBSTACLES.md #21).
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novaops import config  # noqa: E402,F401  (loads the shared .env)
from langfuse import get_client  # noqa: E402


def observations(trace_id: str) -> list:
    api, out, cursor = get_client().api, [], None
    since = datetime.now(timezone.utc) - timedelta(days=30)
    while True:
        page = api.observations.get_many(trace_id=trace_id, fields="core,basic,metadata",
                                         from_start_time=since, limit=100, cursor=cursor)
        out += page.data
        cursor = page.meta.cursor if page.meta else None
        if not cursor or not page.data:
            return out


def main(trace_id: str) -> None:
    obs = sorted(observations(trace_id), key=lambda o: o.start_time)
    if not obs:
        raise SystemExit(f"No observations for trace {trace_id} (ingestion can lag a few minutes).")
    ids = {o.id for o in obs}
    children: dict = {}
    for o in obs:
        parent = o.parent_observation_id if o.parent_observation_id in ids else None
        children.setdefault(parent, []).append(o)
    print(f"trace {trace_id} — {len(obs)} observations\n")

    def show(parent, depth):
        for o in children.get(parent, []):
            print(f"{'  ' * depth}- {o.name}  [{o.type}]  {o.start_time:%H:%M:%S}")
            if depth == 0 and o.metadata:
                for k, v in o.metadata.items():
                    print(f"{'  ' * depth}    {k}: {str(v)[:160]}")
            show(o.id, depth + 1)
    show(None, 0)


if __name__ == "__main__":
    main(sys.argv[1])
