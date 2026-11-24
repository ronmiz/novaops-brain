"""Fail fast, and say why, when the supplied dataset is not where config.py looks for it.

The dataset is never committed (restricted documents). A fresh clone that is not next to the
course folder must point NOVAOPS_DATASET_DIR at it — see README "Data". Without this check the
symptom is three opaque collection errors (vendor/renewal read their schemas at import, #42)."""
import pytest

from novaops import config


def pytest_sessionstart(session):
    if not (config.DOCS_DIR.is_dir() and config.SEED_DIR.is_dir()):
        pytest.exit(f"NovaOps dataset not found at {config.DATASET_DIR}. Set NOVAOPS_DATASET_DIR to the "
                    "novaops-enterprise-agent-dataset folder (README, section 'Data').", returncode=4)
