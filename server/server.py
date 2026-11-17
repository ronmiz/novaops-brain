"""NovaOps MCP server — the tool boundary (spec 6.1: tools behind a server, not
functions stitched into the graph).

Lesson 10's server, repointed at the project dataset. Retrieval is no longer the
small in-memory FAISS index: `search_documents` is the Lesson 7 OpenSearch pipeline
(permission filter -> k-NN -> Nova rerank) over all 7 collections.

    python server/server.py          # http://127.0.0.1:9880/mcp

Tool classes (Milestone 4):
  read     visible to the model when its scope's loadout includes them
  write    create_access_request — released only by the write gate, and refused HERE too
           unless the approval it names is recorded as approved (defence in depth)
  app      request_approval, get_approval — called by application code in the approval
           workflow, never shown to a model (novaops/agent/policy.APP_TOOLS)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from novaops import config, db  # noqa: E402
from novaops.rag import retrieval  # noqa: E402

mcp = FastMCP("novaops-brain", host=config.MCP_BIND_HOST, port=config.MCP_PORT)
POLICIES_DIR = config.DOCS_DIR / "policies"


def cited(rows: list[dict], key: str) -> list[dict]:
    """Every record carries its own ready-made citation. Measured: without it the model
    rarely cited database facts in the required form (docs/OBSTACLES.md #10)."""
    return [{"cite": f"[record: {r[key]}]", **r} for r in rows]


@mcp.tool()
def search_documents(query: str, caller_id: str, collections: list[str] | None = None) -> list[dict]:
    """Search NovaOps documents: policies, internal memos, IT knowledge base, vendor
    contracts, employment records, the employee handbook and the manager playbook.
    Results are already filtered to what the caller may see. Cite every hit you use by
    copying its `cite` value. A newer or more specific document (see `doc_date`)
    overrides an older or more general one.

    Args:
        query: What you need to find, in natural language.
        caller_id: The employee id of the person asking. Supplied by the application.
        collections: Optional narrowing — any of policies, internal_memos, it_kb,
            contracts, employment, handbook, manager_playbook.
    """
    return [{"cite": f"[{h['source']} § {h['section']}]", **h}
            for h in retrieval.search(query, caller_id, collections)]


@mcp.tool()
def list_policies() -> list[str]:
    """List the names of NovaOps's twelve HR and IT policies."""
    return sorted(p.stem for p in POLICIES_DIR.glob("*.md"))


@mcp.tool()
def get_policy(name: str) -> dict:
    """Return the full text of one policy, e.g. 'equipment_policy'. Policies can be
    superseded by later internal memos — check memos when a threshold matters."""
    path = POLICIES_DIR / f"{name}.md"
    if not path.is_file():
        raise ValueError(f"No policy named {name!r}. Call list_policies for valid names.")
    source = f"documents/policies/{path.name}"
    return {"cite": f"[{source} § (whole document)]", "source": source,
            "text": path.read_text(encoding="utf-8")}


@mcp.tool()
def get_employee(query: str) -> list[dict]:
    """Look up employees by id ('E001'), email, or (partial) name. Names collide —
    two people can share a first name; confirm which one is meant."""
    return cited(db.get_employee(query), "employee_id")


@mcp.tool()
def check_software_subscription(software: str) -> list[dict]:
    """Seat usage for a SaaS subscription (seat_limit, active_seats, over_limit),
    plus contract id, annual cost and renewal date. Use when someone cannot get a
    licence. Records seat COUNTS only — not which employee holds a seat."""
    return cited(db.check_software_subscription(software), "subscription_id")


@mcp.tool()
def list_onboarding_tasks(employee_id: str) -> list[dict]:
    """An employee's onboarding checklist — the system of record for joiners. Use it for
    "what's left / what's open" and for "when will I get my laptop / access": each task
    (equipment preparation, Okta, licences) has a status and a due date. Watch for 'blocked'."""
    return cited(db.list_onboarding_tasks(employee_id), "task_id")


@mcp.tool()
def check_asset_inventory(asset_type: str = "", location: str = "") -> list[dict]:
    """Hardware on hand (laptops, monitors, docks, headsets); both filters optional."""
    return cited(db.check_asset_inventory(asset_type, location), "asset_id")


@mcp.tool()
def list_employee_tickets(employee_id: str, status: str = "") -> list[dict]:
    """IT tickets raised by or for one employee. Check here before opening anything new."""
    return cited(db.list_employee_tickets(employee_id, status), "ticket_id")


@mcp.tool()
def list_access_requests(employee_id: str) -> list[dict]:
    """Access requests already filed for one employee, each with the approvals recorded
    against it. Check here before proposing anything new: an existing request is REUSED,
    never duplicated."""
    return cited(db.list_access_requests(employee_id), "request_id")


@mcp.tool()
def check_team_system_access(system: str, caller_id: str) -> dict:
    """For a MANAGER: what is recorded about their direct reports and one system (e.g.
    'Webex') — role entitlement, access requests, onboarding tasks. NovaOps does NOT record
    which employee holds a seat (only seat counts); this tool says so explicitly. Role
    entitlement is not a seat.

    Args:
        system: System name, e.g. Webex.
        caller_id: The manager asking. Supplied by the application.
    """
    out = db.team_system_access(caller_id, system)
    for member in out["team"]:
        member["cite"] = f"[record: {member['employee_id']}]"
    if out["subscription"]:
        out["subscription"]["cite"] = f"[record: {out['subscription']['subscription_id']}]"
    return out


@mcp.tool()
def create_access_request(employee_id: str, system: str, justification: str, approval_id: str) -> dict:
    """WRITE. File an access request against a RECORDED approval. Idempotent: an open request
    for the same employee and system is returned instead of creating a second one."""
    return db.create_access_request(employee_id, system, justification, approval_id)


@mcp.tool()
def request_approval(request_type: str, request_id: str, approver_id: str, reason: str) -> dict:
    """APP. Persist an approval request (idempotent: an open one for the same request is reused)."""
    return db.request_approval(request_type, request_id, approver_id, reason)


@mcp.tool()
def get_approval(approval_id: str) -> dict:
    """APP. One approval row, as recorded."""
    return db.get_approval(approval_id) or {}


if __name__ == "__main__":
    db.connect().close()   # builds var/novaops.db from the seed on first run
    print(f"NovaOps MCP server -> {config.MCP_URL}  (index '{config.INDEX_NAME}', Ctrl-C to stop)")
    mcp.run(transport="streamable-http")
