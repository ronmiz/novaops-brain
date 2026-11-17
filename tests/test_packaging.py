"""Lesson 14 stage without Docker: the entry points refuse bad input before any workflow runs,
and the health endpoints never call a model."""
from fastapi.testclient import TestClient

from novaops import api

client = TestClient(api.app)
OK = {"message": "What is the status of my Webex login ticket?", "caller_id": "E010", "caller_group": "Regular Employee"}


def test_health_needs_nothing():
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_reports_its_dependencies():
    body = client.get("/ready").json()
    assert {"database", "tool_server"} <= set(body)


def test_bad_input_is_refused_before_any_workflow(monkeypatch):
    async def must_not_run(*a, **k):
        raise AssertionError("the agent ran on invalid input")
    monkeypatch.setattr(api, "ask", must_not_run)
    for bad in ({**OK, "message": "   "}, {**OK, "message": "x" * (api.MAX_MESSAGE + 1)},
                {**OK, "caller_id": "Rachel"}, {**OK, "caller_group": "Admins"},
                {**OK, "thread_id": "../etc"}, {"message": "hi"}):
        assert client.post("/ask", json=bad).status_code == 422, bad
    assert client.post("/vendor/extract", json={"document": " ", "source_id": "x"}).status_code == 422


def test_valid_input_calls_the_same_core_function(monkeypatch):
    seen = {}

    async def fake_ask(message, caller_id, caller_group, thread_id):
        seen.update(caller_id=caller_id)
        return {"status": "completed", "answer": "T001 is open [record: T001]", "trace_id": "t1"}
    monkeypatch.setattr(api, "ask", fake_ask)
    r = client.post("/ask", json=OK)
    assert r.status_code == 200 and r.json()["status"] == "completed" and seen == {"caller_id": "E010"}
