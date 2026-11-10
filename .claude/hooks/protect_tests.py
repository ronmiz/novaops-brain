"""PreToolUse hook: a coding agent may ADD tests, never weaken them (CLAUDE.md, Lesson 12 lab).

Denies an Edit/Write under tests/ that removes `assert` statements or adds a skip/xfail marker.
Deterministic, so unlike a skill it always fires. Reads the hook JSON on stdin; prints a
PreToolUse decision; exit code 0 either way.
"""
import json
import re
import sys
from pathlib import Path

WEAKEN = re.compile(r"pytest\.mark\.(skip|xfail)|pytest\.skip\(")


def asserts(text: str) -> int:
    return len(re.findall(r"^\s*assert\b", text or "", re.M))


def verdict(event: dict) -> str | None:
    tool, args = event.get("tool_name"), event.get("tool_input") or {}
    path = Path(args.get("file_path", ""))
    if "tests" not in path.parts:
        return None
    if tool == "Edit":
        old, new = args.get("old_string", ""), args.get("new_string", "")
    elif tool == "Write":
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        new = args.get("content", "")
    else:
        return None
    if asserts(new) < asserts(old):
        return f"removes {asserts(old) - asserts(new)} assert(s) from {path.name} — fix the code, not the test"
    if len(WEAKEN.findall(new)) > len(WEAKEN.findall(old)):
        return f"adds a skip/xfail to {path.name} — fix the code, not the test"
    return None


if __name__ == "__main__":
    reason = verdict(json.load(sys.stdin))
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    sys.exit(0)
