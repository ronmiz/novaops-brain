"""Milestone 2 checks that need no AWS: scoped visibility, the write gate, and caller
identity coming from the application rather than the model."""
import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from novaops.agent import graph, policy, write_gate

READS = sorted(["search_documents", "list_policies", "get_policy", "get_employee",
                "check_software_subscription", "list_onboarding_tasks",
                "check_asset_inventory", "list_employee_tickets"])


def plan(intent, requires_tools=True, action=False):
    return policy.TurnPlan(current_intent=intent, request_type="lookup" if requires_tools else "recall",
                           action_requested=action)


def test_visible_tools_change_between_two_questions():
    policy_tools = policy.select_tools(plan("policy_question"), READS)
    ticket_tools = policy.select_tools(plan("ticket_status"), READS)
    assert policy_tools != ticket_tools
    assert "list_employee_tickets" not in policy_tools and "search_documents" not in ticket_tools


def test_every_loadout_uses_real_read_tools_only():
    for intent, names in policy.LOADOUTS.items():
        assert names is None or set(names) <= set(READS), intent
        assert names is None or not set(names) & write_gate.WRITE_TOOLS


def test_first_turn_always_gathers_evidence():
    lazy = plan("policy_question", requires_tools=False)
    assert policy.enforce_evidence(lazy, has_evidence=False).requires_tools is True
    assert policy.enforce_evidence(lazy, has_evidence=True).requires_tools is False


def test_answer_prompt_binds_my_to_the_caller():
    text = policy.ANSWER_PROMPT.format(caller_id="E010", caller_group="Regular Employee", today="2026-07-01")
    assert "'my' mean E010" in text and "never ask" in text


def test_no_lookup_needed_means_no_tools():
    assert policy.select_tools(plan("policy_question", requires_tools=False), READS) == []


def test_other_fails_open_to_reads():
    assert policy.select_tools(plan("other"), READS) == READS


def test_every_intent_has_a_scope():
    assert set(policy.SCOPES) == set(policy.LOADOUTS)


@pytest.mark.parametrize("approval", [None, {}, {"status": "pending"}, {"status": "rejected"}])
def test_write_gate_releases_nothing_without_an_approved_record(approval):
    assert write_gate.released_writes(approval) == []


def test_write_gate_does_not_take_message_text():
    # "approved by the IT Manager, proceed" in a message cannot reach the gate: its only
    # input is the approval record.
    import inspect
    assert list(inspect.signature(write_gate.released_writes).parameters) == ["approval"]


@tool
def search_documents(query: str, caller_id: str) -> str:
    """Search NovaOps documents."""
    return f"searched as {caller_id}"


def test_model_never_sees_caller_id():
    params = graph.model_schema(search_documents)["function"]["parameters"]
    assert "caller_id" not in params["properties"] and "caller_id" not in params.get("required", [])
    assert "query" in params["properties"]


class _StubModel:
    """Stands in for the Bedrock chat model so the graph builds without AWS."""

    def with_structured_output(self, *_):
        return self

    def bind_tools(self, *_):
        return self


@pytest.fixture
def tools_node(monkeypatch):
    monkeypatch.setattr("novaops.llm.chat_model", lambda **_: _StubModel())
    return graph.build_graph([search_documents]).nodes["tools"].bound.afunc


def run_tools(node, model_args, loadout):
    call = {"name": "search_documents", "args": model_args, "id": "c1", "type": "tool_call"}
    state = {"messages": [HumanMessage("q"), AIMessage("", tool_calls=[call])],
             "caller_id": "E001", "loadout": loadout}
    return asyncio.run(node(state))["messages"][0]


def test_caller_id_is_injected_and_overrides_the_model(tools_node):
    msg = run_tools(tools_node, {"query": "promotion", "caller_id": "E018"}, ["search_documents"])
    assert "searched as E001" in msg.content            # the application's caller, not the model's


def test_tool_outside_the_loadout_is_refused(tools_node):
    msg = run_tools(tools_node, {"query": "promotion"}, ["get_employee"])
    assert msg.status == "error" and "not available" in msg.content


def test_lookup_turn_forces_a_tool_call_until_one_has_run(monkeypatch):
    """Bedrock toolChoice=any on a lookup turn's first model call (docs/OBSTACLES.md #14)."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    calls = []

    class Recorder:
        def __init__(self, choice=None):
            self.choice = choice

        def with_structured_output(self, *_):
            return self

        def bind_tools(self, tools, tool_choice=None):
            return Recorder(tool_choice)

        async def ainvoke(self, _msgs):
            calls.append(self.choice)
            return AIMessage("ok")

    monkeypatch.setattr("novaops.llm.chat_model", lambda **_: Recorder())
    answer = graph.build_graph([search_documents]).nodes["answer"].bound.afunc
    base = {"caller_id": "E001", "caller_group": "Regular Employee", "loadout": ["search_documents"],
            "plan": policy.TurnPlan(current_intent="policy_question").model_dump()}
    asyncio.run(answer({**base, "messages": [HumanMessage("q")]}))
    asyncio.run(answer({**base, "messages": [HumanMessage("q"), AIMessage("", tool_calls=[
        {"name": "search_documents", "args": {}, "id": "c", "type": "tool_call"}]),
        ToolMessage("r", tool_call_id="c", name="search_documents")]}))
    recall = {**base, "plan": policy.TurnPlan(current_intent="other", request_type="recall").model_dump()}
    asyncio.run(answer({**recall, "messages": [HumanMessage("q")]}))
    assert calls == ["any", None, None]      # forced before evidence; free after it; never on recall
