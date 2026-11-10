"""Prove this machine reaches the Langfuse project BEFORE a run that would record nothing
(Lesson 11, exercise 1). With no keys the client is a silent no-op; with wrong keys the
exporter drops batches in a background thread. Both look like a working agent.

    python scripts/check_langfuse.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novaops import config  # noqa: E402,F401  (loads lessons/.env)
from langfuse import get_client  # noqa: E402

missing = [n for n in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL") if not os.getenv(n)]
if missing:
    raise SystemExit(f"Missing in lessons/.env: {', '.join(missing)}")
try:
    ok = get_client().auth_check()
except Exception:
    ok = False
if not ok:
    raise SystemExit("Langfuse rejected the keys: check the pair is from the SAME project and "
                     "LANGFUSE_BASE_URL matches its region (EU = https://cloud.langfuse.com).")
print(f"[connected] {os.environ['LANGFUSE_BASE_URL']} (keys read from .env, never printed)")
