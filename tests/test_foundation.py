"""Milestone 1 checks that need no AWS: corpus metadata, the manager rule, the
permission filter. Run:  python -m pytest -q
"""
import pytest

from novaops import config, db
from novaops.rag import documents, retrieval

pytestmark = pytest.mark.skipif(not config.DOCS_DIR.is_dir(), reason="dataset folder not found")


@pytest.fixture(scope="module")
def chunks():
    return documents.load_chunks(config.DOCS_DIR)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "novaops.db")
    db.reseed()


def test_all_102_documents_are_chunked(chunks):
    assert len({c["source"] for c in chunks}) == 102


def test_manager_playbook_is_restricted_everything_else_open(chunks):
    by_source = {c["source"]: c["audience"] for c in chunks}
    restricted = {s for s, a in by_source.items() if a == "manager"}
    assert restricted == {s for s in by_source if s.startswith("documents/manager_playbook/")}
    assert len(restricted) == 17
    assert len(by_source) - len(restricted) == 85   # 70 unlabelled + 15 handbook (all)


def test_restricted_collection_fails_closed_without_front_matter():
    assert documents.audience_for("manager_playbook", {}) == "manager"
    assert documents.audience_for("policies", {}) == "all"


def test_sources_use_golden_dataset_paths(chunks):
    assert any(c["source"] == "documents/it_kb/mfa_reset.md" for c in chunks)


def test_memo_date_is_extracted(chunks):
    memo = next(c for c in chunks if c["source"].endswith("saas_renewal_freeze_q3.md"))
    assert memo["doc_date"] == "2026-06-25"


@pytest.mark.parametrize("caller, expected", [
    ("E018", True),    # Yael Romano: UG_REGULAR but manages Maya, Noam, Rachel
    ("E004", True),    # Sara Ben-David manages Sara Cohen and Maya Rosen
    ("E001", False),   # Maya Cohen
    ("E010", False),   # Rachel Stein
    ("E999", False),   # unknown caller -> not a manager (fail closed)
])
def test_manager_is_derived_from_manager_id(caller, expected):
    assert db.is_manager(caller) is expected


def test_non_manager_filter_admits_only_audience_all():
    assert retrieval.build_filter("E001") == {"bool": {"must": [{"term": {"audience": "all"}}]}}


def test_manager_filter_is_unrestricted():
    assert retrieval.build_filter("E018") is None


def test_reseed_restores_seed_state():
    assert [r["request_id"] for r in db._rows("SELECT request_id FROM access_requests")] == \
        ["AR001", "AR002", "AR003", "AR004"]


def _ranked(*pairs):
    return [({"source": s, "section": "x", "title": "t", "text": "..."}, score) for s, score in pairs]


def test_cut_respects_threshold_and_max():
    ranked = _ranked(("a", 0.9), ("b", 0.8), ("c", 0.55), ("d", 0.5))
    assert [h["source"] for h in retrieval.cut(ranked, min_score=0.6)] == ["a", "b"]
    assert len(retrieval.cut(ranked, min_score=0.0, max_results=3)) == 3


def test_cut_per_doc_stops_one_document_crowding_out_others():
    ranked = _ranked(("a", 0.95), ("a", 0.9), ("a", 0.85), ("b", 0.8))
    assert [h["source"] for h in retrieval.cut(ranked, per_doc=1)] == ["a", "b"]
    assert [h["source"] for h in retrieval.cut(ranked, per_doc=None)] == ["a", "a", "a", "b"]


def test_short_documents_stay_whole_long_ones_split(chunks):
    by_source = {}
    for c in chunks:
        by_source.setdefault(c["source"], []).append(c)
    mfa = by_source["documents/it_kb/mfa_reset.md"]
    assert len(mfa) == 1 and "MFA Reset" in mfa[0]["text"]       # title stays with the steps
    assert len(by_source["documents/handbook/making-a-career.md"]) > 1
    assert all(len(v) == 1 for k, v in by_source.items()
               if not k.startswith(("documents/handbook/", "documents/manager_playbook/")))
