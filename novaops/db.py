"""The operational database (SQLite file) and its read queries.

Built from the supplied schema.sql + seed.sql. `reseed()` restores the seed state —
the evaluation run reseeds before every independent case (spec section 13).
The queries are Lesson 10's server/db.py, repointed at the project dataset.
"""
import difflib
import re
import sqlite3
from contextlib import closing

from . import config

EMPLOYEE_FIELDS = (
    "employee_id, full_name, email, role, department_id, manager_id, "
    "location, employment_type, status, start_date, user_group_id, systems_allowed_by_role"
)


def reseed() -> None:
    """(Re)build the database from the seed. schema.sql starts with DROP TABLE, so
    running it over an existing file resets it."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A fresh file: the seed's DROP TABLEs do not cover the renewal workflow's own tables.
    config.DB_PATH.unlink(missing_ok=True)
    with closing(sqlite3.connect(config.DB_PATH)) as conn:
        conn.executescript((config.SEED_DIR / "schema.sql").read_text(encoding="utf-8"))
        conn.executescript((config.SEED_DIR / "seed.sql").read_text(encoding="utf-8"))
        conn.commit()


def connect() -> sqlite3.Connection:
    if not config.DB_PATH.exists():
        reseed()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with closing(connect()) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def is_manager(employee_id: str) -> bool:
    """A caller is a manager when some employee's manager_id is their id (spec 12).
    NOT derivable from user_group: Yael Romano (E018) manages people but is UG_REGULAR."""
    return bool(_rows("SELECT 1 FROM employees WHERE manager_id = ? LIMIT 1", (employee_id,)))


def get_employee(query: str) -> list[dict]:
    """Every match — first names collide on purpose (two Mayas, two Saras, two Daniels).
    No exact match -> the closest full-name spellings, flagged as such (S8: "rrachel stein")."""
    rows = _rows(
        f"SELECT {EMPLOYEE_FIELDS} FROM employees "
        "WHERE employee_id = ? OR lower(email) = lower(?) OR lower(full_name) LIKE lower(?) "
        "ORDER BY full_name",
        (query, query, f"%{query}%"),
    )
    if rows:
        return rows
    names = {r["full_name"].lower(): r["full_name"] for r in _rows("SELECT full_name FROM employees")}
    close = difflib.get_close_matches(query.strip().lower(), list(names), n=3, cutoff=0.8)
    return [{**r, "matched_by": f"closest spelling to {query!r}"}
            for name in close for r in _rows(f"SELECT {EMPLOYEE_FIELDS} FROM employees WHERE full_name = ?",
                                             (names[name],))]


def ids_by_full_name() -> dict[str, str]:
    """Full name -> employee id, for tagging documents at ingest (#35)."""
    return {r["full_name"]: r["employee_id"] for r in _rows("SELECT full_name, employee_id FROM employees")}


def people_named(text: str) -> list[str]:
    """Full names of employees whose first or last name appears as a capitalised word in
    `text` ("Maya's offer letter" -> Maya Cohen and the other Maya). Used by retrieval (#33)."""
    words = set(re.findall(r"\b[A-Z][a-z]{2,}\b", text))
    return [r["full_name"] for r in _rows("SELECT full_name FROM employees ORDER BY full_name")
            if words & set(r["full_name"].split())]


def check_software_subscription(software: str) -> list[dict]:
    """Matches the system or vendor name. A descriptive query ('Webex standard user license')
    falls back to its words, so it still finds Webex instead of returning nothing (#29)."""
    rows = _subscriptions(software)
    for word in (w for w in re.findall(r"[A-Za-z]{4,}", software) if not rows):
        rows = _subscriptions(word)
    return rows


def _subscriptions(software: str) -> list[dict]:
    like = f"%{software}%"
    rows = _rows(
        "SELECT sub.subscription_id, sub.contract_id, sys.system_name, v.vendor_name, "
        "       sub.seat_limit, sub.active_seats, sub.status, sub.renewal_date, "
        "       sub.annual_cost, sub.owner_department_id "
        "FROM software_subscriptions sub "
        "JOIN systems sys ON sub.system_id = sys.system_id "
        "JOIN vendors v ON sub.vendor_id = v.vendor_id "
        "WHERE lower(sys.system_name) LIKE lower(?) OR lower(v.vendor_name) LIKE lower(?) "
        "ORDER BY sys.system_name",
        (like, like),
    )
    for sub in rows:
        sub["seats_available"] = sub["seat_limit"] - sub["active_seats"]
        sub["over_limit"] = sub["active_seats"] >= sub["seat_limit"]
    return rows


def list_onboarding_tasks(employee_id: str) -> list[dict]:
    return _rows(
        "SELECT task_id, task_type, description, owner_group, status, due_date, related_system_id "
        "FROM onboarding_tasks WHERE employee_id = ? ORDER BY due_date, task_id",
        (employee_id,),
    )


def check_asset_inventory(asset_type: str = "", location: str = "") -> list[dict]:
    return _rows(
        "SELECT asset_id, asset_type, model, status, location, employee_id, notes FROM assets "
        "WHERE lower(asset_type) LIKE lower(?) AND lower(location) LIKE lower(?) "
        "ORDER BY asset_type, asset_id",
        (f"%{asset_type}%", f"%{location}%"),
    )


def list_employee_tickets(employee_id: str, status: str = "") -> list[dict]:
    return _rows(
        "SELECT ticket_id, category, subcategory, priority, status, subject, "
        "       created_at, assigned_team, related_system_id "
        "FROM tickets WHERE employee_id = ? AND lower(status) LIKE lower(?) "
        "ORDER BY created_at DESC",
        (employee_id, f"%{status}%"),
    )


# --- Webex: access requests, approvals, the seat gap (Milestone 4) -----------------
# Writes are idempotent by a natural key, and every write leaves an audit_log row.
# Timestamps use the pinned clock (spec 13), so a replay writes identical rows.

OPEN_REQUEST = ("blocked", "pending_approval", "planned", "submitted", "approved")
OPEN_APPROVAL = ("needed", "pending")


def _now() -> str:
    return f"{config.TODAY}T12:00:00Z"


def _next_id(conn, table: str, column: str, prefix: str) -> str:
    ids = [r[0] for r in conn.execute(f"SELECT {column} FROM {table} WHERE {column} LIKE ?", (f"{prefix}%",))]
    n = max((int(i[len(prefix):]) for i in ids if i[len(prefix):].isdigit()), default=0) + 1
    return f"{prefix}{n:03d}"


def _audit(conn, entity_type: str, entity_id: str, event: str, actor: str | None, notes: str) -> None:
    conn.execute("INSERT INTO audit_log (event_id, entity_type, entity_id, event_type, actor_employee_id, "
                 "created_at, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (_next_id(conn, "audit_log", "event_id", "EV"), entity_type, entity_id, event, actor, _now(), notes))


def system_id(name: str) -> str | None:
    rows = _rows("SELECT system_id FROM systems WHERE lower(system_name) = lower(?) OR system_id = ?", (name, name))
    return rows[0]["system_id"] if rows else None


def list_access_requests(employee_id: str) -> list[dict]:
    """An employee's access requests, each with the approvals recorded against it."""
    requests = _rows(
        "SELECT ar.request_id, ar.employee_id, sys.system_name, ar.access_level, ar.business_justification, "
        "       ar.status, ar.approver_id, ar.created_at, ar.decision_reason "
        "FROM access_requests ar JOIN systems sys ON ar.system_id = sys.system_id "
        "WHERE ar.employee_id = ? ORDER BY ar.created_at", (employee_id,))
    for r in requests:
        r["approvals"] = _rows("SELECT approval_id, request_type, approver_id, status, decision_reason "
                               "FROM approvals WHERE request_id = ? ORDER BY approval_id", (r["request_id"],))
    return requests


def team_system_access(manager_id: str, system: str) -> dict:
    """What IS recorded about a manager's direct reports and one system. Seat ASSIGNMENTS
    are not: software_subscriptions holds counts only (spec 13, W-I-02)."""
    sid = system_id(system)
    sub = _rows("SELECT subscription_id, seat_limit, active_seats FROM software_subscriptions WHERE system_id = ?", (sid,))
    team = []
    for e in _rows("SELECT employee_id, full_name, role, status, systems_allowed_by_role FROM employees "
                   "WHERE manager_id = ? ORDER BY employee_id", (manager_id,)):
        team.append({
            "employee_id": e["employee_id"], "full_name": e["full_name"], "role": e["role"], "status": e["status"],
            "entitled_by_role": system.lower() in e["systems_allowed_by_role"].lower(),
            "seat_assignment": "not recorded",
            "access_requests": _rows("SELECT request_id, status, decision_reason FROM access_requests "
                                     "WHERE employee_id = ? AND system_id = ?", (e["employee_id"], sid)),
            "onboarding_tasks": _rows("SELECT task_id, status, description FROM onboarding_tasks "
                                      "WHERE employee_id = ? AND related_system_id = ?", (e["employee_id"], sid)),
        })
    return {"system": system, "seat_assignments_recorded": False,
            "note": "NovaOps records seat COUNTS per subscription, not which employee holds a seat. "
                    "Role entitlement (systems_allowed_by_role) is not a seat.",
            "subscription": sub[0] if sub else None, "team": team}


def get_approval(approval_id: str) -> dict | None:
    rows = _rows("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
    return rows[0] if rows else None


def request_approval(request_type: str, request_id: str, approver_id: str, reason: str) -> dict:
    """Idempotent: an approval still open for the same request is reused, never duplicated."""
    with closing(connect()) as conn:
        open_ = conn.execute(
            f"SELECT * FROM approvals WHERE request_id = ? AND request_type = ? AND approver_id = ? "
            f"AND status IN ({','.join('?' * len(OPEN_APPROVAL))}) ORDER BY approval_id LIMIT 1",
            (request_id, request_type, approver_id, *OPEN_APPROVAL)).fetchone()
        if open_:
            return {**dict(open_), "reused": True}
        aid = _next_id(conn, "approvals", "approval_id", "AP")
        conn.execute("INSERT INTO approvals (approval_id, request_type, request_id, approver_id, status, "
                     "decision_reason, created_at) VALUES (?, ?, ?, ?, 'needed', ?, ?)",
                     (aid, request_type, request_id, approver_id, reason, _now()))
        _audit(conn, "approval", aid, "approval_requested", None, reason)
        conn.commit()
    return {**get_approval(aid), "reused": False}


def record_approval(approval_id: str, approver_id: str, approved: bool, reason: str = "") -> dict:
    """The HUMAN channel: only the approver named on the row may decide it. Re-recording the
    same decision is a no-op; changing a closed decision is refused."""
    row = get_approval(approval_id)
    if row is None:
        raise ValueError(f"No approval {approval_id}.")
    if row["approver_id"] != approver_id:
        raise PermissionError(f"{approval_id} can only be decided by {row['approver_id']}, not {approver_id}.")
    status = "approved" if approved else "rejected"
    if row["status"] == status:
        return row
    if row["status"] not in OPEN_APPROVAL:
        raise ValueError(f"{approval_id} is already {row['status']}.")
    with closing(connect()) as conn:
        conn.execute("UPDATE approvals SET status = ?, decision_reason = ? WHERE approval_id = ?",
                     (status, reason or row["decision_reason"], approval_id))
        _audit(conn, "approval", approval_id, f"approval_{status}", approver_id, reason)
        conn.commit()
    return get_approval(approval_id)


def create_access_request(employee_id: str, system: str, justification: str, approval_id: str) -> dict:
    """THE write. Fail closed: refused unless `approval_id` is recorded as approved.
    Idempotent: an open request for the same employee and system is returned, not duplicated
    (Rachel already has AR001)."""
    approval = get_approval(approval_id)
    if not approval or approval["status"] != "approved":
        raise PermissionError(f"Refused: approval {approval_id} is not recorded as approved.")
    sid = system_id(system)
    if sid is None:
        raise ValueError(f"Unknown system {system!r}.")
    with closing(connect()) as conn:
        existing = conn.execute(
            f"SELECT * FROM access_requests WHERE employee_id = ? AND system_id = ? "
            f"AND status IN ({','.join('?' * len(OPEN_REQUEST))}) ORDER BY request_id LIMIT 1",
            (employee_id, sid, *OPEN_REQUEST)).fetchone()
        if existing:
            return {**dict(existing), "reused": True}
        rid = _next_id(conn, "access_requests", "request_id", "AR")
        conn.execute("INSERT INTO access_requests (request_id, employee_id, system_id, access_level, "
                     "business_justification, status, approver_id, created_at, decision_reason) "
                     "VALUES (?, ?, ?, 'standard_user', ?, 'submitted', ?, ?, ?)",
                     (rid, employee_id, sid, justification, approval["approver_id"], _now(),
                      f"Filed against recorded approval {approval_id}."))
        _audit(conn, "access_request", rid, "access_request_created", approval["approver_id"], approval_id)
        conn.commit()
        return {**dict(conn.execute("SELECT * FROM access_requests WHERE request_id = ?", (rid,)).fetchone()),
                "reused": False}
