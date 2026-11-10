"""The operational database (SQLite file) and its read queries.

Built from the supplied schema.sql + seed.sql. `reseed()` restores the seed state —
the evaluation run reseeds before every independent case (spec section 13).
The queries are Lesson 10's server/db.py, repointed at the project dataset.
"""
import sqlite3
from contextlib import closing

from . import config

EMPLOYEE_FIELDS = (
    "employee_id, full_name, email, role, department_id, manager_id, "
    "location, employment_type, status, start_date, user_group_id"
)


def reseed() -> None:
    """(Re)build the database from the seed. schema.sql starts with DROP TABLE, so
    running it over an existing file resets it."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
    """Every match — first names collide on purpose (two Mayas, two Saras, two Daniels)."""
    return _rows(
        f"SELECT {EMPLOYEE_FIELDS} FROM employees "
        "WHERE employee_id = ? OR lower(email) = lower(?) OR lower(full_name) LIKE lower(?) "
        "ORDER BY full_name",
        (query, query, f"%{query}%"),
    )


def check_software_subscription(software: str) -> list[dict]:
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
