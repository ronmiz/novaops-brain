"""Thin HTTP entry points (Lesson 14 stage): validate, call the SAME core functions the tests
and the CLI call, return a typed response. No second path into any workflow.

    uvicorn novaops.api:app --port 8000

    POST /ask              one agent turn  -> run.ask()
    POST /vendor/extract   one document    -> vendor.extract()
    GET  /health           liveness: the process answers. No model call, no I/O.
    GET  /ready            readiness: database file present, tool server port reachable. No model call.

Bad input is refused here, before any workflow runs: blank or oversized text, a malformed
employee id, an unknown user group.
"""
import socket
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator

from . import config, vendor
from .agent.contracts import Status
from .agent.run import ask

app = FastAPI(title="NovaOps Company Brain", version="1.0")
MAX_MESSAGE, MAX_DOCUMENT = 8_000, 50_000
Group = Literal["Regular Employee", "HR Group", "IT Group"]


def _not_blank(v: str) -> str:
    if not v.strip():
        raise ValueError("must not be blank")
    return v


class AskRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE)
    caller_id: str = Field(pattern=r"^E\d{3}$")
    caller_group: Group
    thread_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    _blank = field_validator("message")(_not_blank)


class AskResponse(BaseModel):
    status: Status
    answer: str
    thread_id: str | None = None
    request_id: str | None = None
    intent: str | None = None
    tools_used: list[str] = []
    access_decision: dict | None = None
    trace_id: str | None = None


class VendorRequest(BaseModel):
    document: str = Field(max_length=MAX_DOCUMENT)
    source_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$")
    _blank = field_validator("document")(_not_blank)


@app.post("/ask", response_model=AskResponse)
async def ask_endpoint(req: AskRequest) -> AskResponse:
    r = await ask(req.message, req.caller_id, req.caller_group, req.thread_id)
    return AskResponse(**{k: r.get(k) for k in AskResponse.model_fields if r.get(k) is not None})


@app.post("/vendor/extract")
def vendor_endpoint(req: VendorRequest) -> dict:
    return vendor.extract(req.document, req.source_id)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    checks = {"database": config.DB_PATH.exists()}
    try:
        with socket.create_connection((config.MCP_HOST, config.MCP_PORT), timeout=1):
            checks["tool_server"] = True
    except OSError:
        checks["tool_server"] = False
    ok = all(checks.values())
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "ready" if ok else "not_ready", **checks}, status_code=200 if ok else 503)
