"""Paths, model ids and endpoints — the only place that reads the environment.

The `.env` lives ONE level above this repo (`lessons/.env`, shared by every lesson);
`find_dotenv()` climbs from this file and finds it. Nothing secret is ever written here.
"""
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

# Langfuse's default export timeout is a few seconds; a slow upload dropped a span batch
# during a golden replay (docs/OBSTACLES.md #12). Traces are the submission, so be patient.
os.environ.setdefault("LANGFUSE_TIMEOUT", "30")

ROOT = Path(__file__).resolve().parents[1]

# The supplied dataset is NOT copied into this repo (it contains restricted documents
# that must never be committed). Default: the course folder next to this repo.
DATASET_DIR = Path(os.environ.get(
    "NOVAOPS_DATASET_DIR",
    ROOT.parent / "Final Project - Company Brain" / "project" / "novaops-enterprise-agent-dataset",
))
DOCS_DIR = DATASET_DIR / "documents"
SEED_DIR = DATASET_DIR / "database"

# Operational database: a FILE, not :memory: — approvals and writes must survive a restart.
DB_PATH = Path(os.environ.get("NOVAOPS_DB_PATH", ROOT / "var" / "novaops.db"))

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
EMBED_MODEL_ID = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBED_DIM = 1024

# Same collection as Lesson 7 (novaops-rag); a NEW index so Lesson 7 / Etz Chaim stay intact.
INDEX_NAME = os.environ.get("NOVAOPS_INDEX", "novaops-brain-kb")

MCP_HOST = "127.0.0.1"
MCP_PORT = int(os.environ.get("NOVAOPS_MCP_PORT", "9880"))
MCP_URL = f"http://{MCP_HOST}:{MCP_PORT}/mcp"
