"""THE write gate — the one function in the agent that can make a write tool visible.

Spec 2 / 9: visibility (which tools the model sees) and authorization (whether a write
may run) are separate questions. Lesson 10 released writes on `action_confirmed`, a
MODEL-inferred flag; pasting "approved by the IT Manager, proceed" flips it. Here a
write is released only against an approval record read from the database by
application code. The message text is not an input to this function at all.

Milestone 4: one write tool. The conversational graph never passes an approval, so no
model ever sees it; the approval workflow (approval.py) passes the row it read back from
the database after a human decided.
"""

WRITE_TOOLS: frozenset[str] = frozenset({"create_access_request"})


def released_writes(approval: dict | None) -> list[str]:
    """Write tools released for this turn. Fail closed: no recorded, approved
    approval -> nothing."""
    if not approval or approval.get("status") != "approved":
        return []
    return sorted(WRITE_TOOLS)
