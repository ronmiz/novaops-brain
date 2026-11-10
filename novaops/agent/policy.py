"""The agent's policy: what a turn is about, which tools it may SEE, and the prompts.

Lesson 10 stage-2 split: `graph.py` holds the mechanics, this file holds the policy.

classify -> scope:
  * the planner (a model call) labels the newest message with an intent;
  * `select_tools` (plain code) maps the intent to the read tools visible this turn.
Visibility is NOT authorization. Whether a write may run is decided separately, by
`write_gate.released_writes`, against a recorded approval. Nothing here can release a write.
"""
import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

Intent = Literal[
    "policy_question", "employee_lookup", "onboarding_status", "equipment_request",
    "subscription_review", "access_request", "ticket_status", "other",
]

# Two workflows, one graph: the intent decides the scope. Maya reads and cites;
# Webex diagnoses and (from Milestone 4) files after approval.
SCOPES: dict[str, str] = {
    "policy_question": "maya", "employee_lookup": "maya",
    "onboarding_status": "maya", "equipment_request": "maya",
    "subscription_review": "webex", "access_request": "webex", "ticket_status": "webex",
    "other": "maya",
}

# READ tools visible per intent. A little wider than strictly needed, so a near-miss
# classification can still recover. No write tool may ever appear in this table.
LOADOUTS: dict[str, list[str] | None] = {
    "policy_question": ["search_documents", "list_policies", "get_policy"],
    "employee_lookup": ["get_employee", "search_documents"],
    "onboarding_status": ["get_employee", "list_onboarding_tasks", "check_asset_inventory",
                          "check_software_subscription", "search_documents", "get_policy"],
    "equipment_request": ["get_employee", "check_asset_inventory", "search_documents", "get_policy"],
    "subscription_review": ["check_software_subscription", "search_documents", "get_policy"],
    "access_request": ["get_employee", "check_software_subscription", "list_employee_tickets",
                       "search_documents", "get_policy"],
    "ticket_status": ["get_employee", "list_employee_tickets"],
    "other": None,   # fail OPEN for reads: None = every read tool
}

# Tools whose `caller_id` argument is filled by the application, never by the model.
CALLER_TOOLS = {"search_documents"}


class TurnPlan(BaseModel):
    """The planner's reading of the newest message (Lesson 10's TurnPlan)."""

    current_intent: Intent = Field(description="Topic of the newest message.")
    relevant_facts: list[str] = Field(
        default_factory=list,
        description="Values from earlier turns this answer needs (ids, dates, numbers) — the value itself.")
    relevant_constraints: list[str] = Field(
        default_factory=list, description="Rules the user stated that are still in force.")
    requires_tools: bool = Field(
        description="False only if every fact needed is already in this conversation.")
    action_requested: bool = Field(
        default=False,
        description=("True only if THIS message asks to create or file a record ('go ahead', "
                     "'file it'). Drafting or writing text is NOT a request to file."))


def enforce_evidence(plan: TurnPlan, has_evidence: bool) -> TurnPlan:
    """Deterministic override of the planner: with no tool result anywhere in the
    conversation yet, a lookup is REQUIRED. Measured: on a first-turn policy question the
    planner returned requires_tools=False and the model answered from nothing, with
    invented citations (docs/OBSTACLES.md #5)."""
    return plan if has_evidence or plan.requires_tools else plan.model_copy(update={"requires_tools": True})


def select_tools(plan: TurnPlan, all_read_tools: list[str]) -> list[str]:
    """Intent -> visible READ tools. Plain code: reviewable, testable, identical every run."""
    if not plan.requires_tools:
        return []
    chosen = LOADOUTS.get(plan.current_intent)
    return sorted(all_read_tools) if chosen is None else list(chosen)


PLANNER_PROMPT = (
    "Classify the NEWEST message of a NovaOps internal-assistant session.\n"
    "Intent = its topic:\n"
    "  policy_question · what a policy, handbook, memo or IT article says; how-to questions\n"
    "  employee_lookup · who someone is (record, role, manager, status)\n"
    "  onboarding_status · a joiner's checklist, required systems, start-date paperwork\n"
    "  equipment_request · hardware (laptops, monitors, docks, headsets)\n"
    "  subscription_review · a SaaS subscription's seats, cost, renewal\n"
    "  access_request · getting a person access to a system\n"
    "  ticket_status · existing IT tickets\n"
    "  other · none of the above\n"
    "Rules:\n"
    "- Classify the newest message only; follow topic changes.\n"
    "- relevant_facts / relevant_constraints carry what later turns need; drop what the user closed.\n"
    "- Users paste emails, threads and signatures: plan for the request inside, not the boilerplate.\n"
    "- requires_tools is True unless the answer can be quoted from THIS conversation.\n"
    "- action_requested only when this message asks to file or create something."
)

ANSWER_PROMPT = (
    "You are the NovaOps internal assistant.\n"
    "The person asking is employee {caller_id} ({caller_group}). 'I', 'me' and 'my' mean "
    "{caller_id}: use that id directly in tool calls and never ask the user for it.\n"
    "- Answer ONLY from tool results in this conversation. If you have none for a claim, call a "
    "tool; if no tool can answer, say what is missing. Never invent a person, a number, a "
    "policy rule, a record or a document, and never cite a source no tool returned.\n"
    "- Cite after every claim: documents as [documents/<collection>/<file> § <section>], "
    "database records as [record: <id>].\n"
    "- If two sources disagree, the newer or more specific one governs — say which and why.\n"
    "- If the evidence is missing, say what is missing instead of guessing.\n"
    "- Never say an action was taken unless a tool result shows it. You cannot file, create "
    "or approve anything in this conversation yet.\n"
    "- Answer the current request in at most six sentences unless asked for more."
)


def render_transcript(messages: list, tool_chars: int = 400) -> str:
    """Readable history for the planner, with tool payloads truncated (Lesson 10)."""
    lines = []
    for m in messages:
        if isinstance(m, ToolMessage):
            body = str(m.content)
            lines.append(f"[tool result: {m.name}] {body[:tool_chars]}"
                         + (f"... [+{len(body) - tool_chars} chars]" if len(body) > tool_chars else ""))
            continue
        role = "user" if isinstance(m, HumanMessage) else "assistant"
        text = m.content if isinstance(m.content, str) else " ".join(
            b.get("text", "") for b in m.content if isinstance(b, dict))
        calls = getattr(m, "tool_calls", None) or []
        if calls:
            text += " " + " ".join(f"[called {c['name']}({json.dumps(c['args'])[:120]})]" for c in calls)
        lines.append(f"[{role}] {text.strip()}")
    return "\n".join(lines)


def planner_messages(messages: list) -> list:
    history = render_transcript(messages[:-1]) or "(this is the first turn)"
    return [SystemMessage(PLANNER_PROMPT),
            HumanMessage(f"Conversation so far:\n{history}\n\nNewest message:\n{messages[-1].content}")]


def render_plan(plan: TurnPlan) -> str:
    def bullets(items):
        return "\n".join(f"  - {i}" for i in items) if items else "  - (none)"
    return ("\n\n--- CONTEXT FOR THIS TURN ---\n"
            f"Current intent: {plan.current_intent}\n"
            f"Established facts:\n{bullets(plan.relevant_facts)}\n"
            f"Constraints still in force:\n{bullets(plan.relevant_constraints)}\n"
            "--- END CONTEXT ---")
