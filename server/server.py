"""NovaOps MCP server — the tool boundary (spec 6.1: tools behind a server, not
functions stitched into the graph).

Lesson 10's server, repointed at the project dataset. Retrieval is no longer the
small in-memory FAISS index: `search_documents` is the Lesson 7 OpenSearch pipeline
(permission filter -> k-NN -> Nova rerank) over all 7 collections.

    python server/server.py          # http://127.0.0.1:9880/mcp

Milestone 1 ships READ tools only. Write tools (access request, approval request,
ticket) arrive with the write gate in Milestones 2 and 4.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from novaops import config, db  # noqa: E402
from novaops.rag import retrieval  # noqa: E402

mcp = FastMCP("novaops-brain", host=config.MCP_HOST, port=config.MCP_PORT)
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


if __name__ == "__main__":
    db.connect().close()   # builds var/novaops.db from the seed on first run
    print(f"NovaOps MCP server -> {config.MCP_URL}  (index '{config.INDEX_NAME}', Ctrl-C to stop)")
    mcp.run(transport="streamable-http")
