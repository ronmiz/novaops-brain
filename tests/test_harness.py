"""The project's own agent controls (spec section 4): the hook that stops a coding agent from
weakening tests."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "protect_tests", Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "protect_tests.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


def edit(old, new, path="tests/test_x.py"):
    return {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old, "new_string": new}}


def test_removing_an_assert_is_denied():
    assert hook.verdict(edit("    assert a == 1\n    assert b == 2\n", "    assert a == 1\n"))


def test_adding_a_skip_is_denied():
    assert hook.verdict(edit("def test_x():\n", "@pytest.mark.skip\ndef test_x():\n"))


def test_adding_a_test_and_editing_code_are_allowed():
    assert hook.verdict(edit("    assert a\n", "    assert a\n    assert b\n")) is None
    assert hook.verdict(edit("x = 1", "x = 2", path="novaops/agent/policy.py")) is None
