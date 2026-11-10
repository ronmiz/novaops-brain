# CLAUDE.md — NovaOps Company Brain

The spec is `../Final Project - Company Brain/project/PROJECT-DESCRIPTION.md`. Read the section
for the milestone you are working on before changing code.

## Non-negotiables
- Every model call goes through `novaops/llm.py`. Nothing else creates a bedrock-runtime client.
- Tools live behind the MCP server (`server/server.py`); the agent never imports `novaops.db` directly.
- Caller identity and user group are application inputs — never ask the model for them.
- The permission filter lives ONCE, in `novaops/rag/retrieval.py`, inside the k-NN query.
- A model may propose an action; only application code records that it happened.
- Every write is idempotent. A write is released only against a recorded approval row.
- Never commit `.env`, keys, `var/`, or anything from the dataset folder.

## Conventions
- Run from the repo root. Windows + Git Bash; `export PYTHONUTF8=1` when piping output to a file.
- `python -m pytest -q` must stay green and needs no AWS. Never weaken or delete a test to make it pass.
- Source paths are `documents/<collection>/<file>.md` — the form GOLDEN-DATASETS.json uses.
- Record a non-obvious decision as a new numbered ADR in `docs/adr/`; never edit an old one.
- Every obstacle (error, wrong assumption, environment trap) gets a row in `docs/OBSTACLES.md`: symptom, root cause, fix, evidence.
