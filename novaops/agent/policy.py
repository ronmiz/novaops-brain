"""The agent's policy: what a turn is about, which tools it may SEE, and the prompts.

Lesson 10 stage-2 split: `graph.py` holds the mechanics, this file holds the policy.

classify -> scope:
  * the planner (a model call) labels the newest message with an intent;
  * `select_tools` (plain code) maps the intent to the read tools visible this turn.
Visibility is NOT authorization. Whether a write may run is decided separately, by
`write_gate.released_writes`, against a recorded approval. Nothing here can release a write.
"""
import json
import re
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
    # A threshold question needs the amount it is compared with (S2 t9: 7,500 vs 18,400) (#18).
    "policy_question": ["search_documents", "list_policies", "get_policy", "check_software_subscription"],
    "employee_lookup": ["get_employee", "search_documents"],
    "onboarding_status": ["get_employee", "list_onboarding_tasks", "check_asset_inventory",
                          "check_software_subscription", "search_documents", "get_policy"],
    # Users call a Webex seat "equipment" too: the subscription tool must be reachable (#17).
    "equipment_request": ["get_employee", "check_asset_inventory", "list_onboarding_tasks",
                          "check_software_subscription", "search_documents", "get_policy"],
    "subscription_review": ["check_software_subscription", "check_team_system_access",
                            "search_documents", "get_policy"],
    "access_request": ["get_employee", "check_software_subscription", "list_employee_tickets",
                       "list_access_requests", "search_documents", "get_policy"],
    "ticket_status": ["get_employee", "list_employee_tickets", "list_access_requests"],
    "other": None,   # fail OPEN for reads: None = every read tool
}

# Tools whose `caller_id` argument is filled by the application, never by the model.
CALLER_TOOLS = {"search_documents", "check_team_system_access"}
# Called by application code in the approval workflow; never visible to any model.
APP_TOOLS = frozenset({"request_approval", "get_approval"})


RequestType = Literal["lookup", "recall", "summary", "draft", "pasted_text", "action"]


class TurnPlan(BaseModel):
    """The planner's reading of the newest message (Lesson 10's TurnPlan).

    Measured (docs/OBSTACLES.md #12): asked a yes/no "does this need a tool?", the planner
    said no on new-topic lookups and the answer model invented facts. So the planner now
    CLASSIFIES the request, and code derives whether evidence must be gathered."""

    current_intent: Intent = Field(description="Topic of the newest message.")
    request_type: RequestType = Field(
        default="lookup",
        description=("lookup = needs a record or document (DEFAULT, and always for a new topic or "
                     "'what is the state now'); recall = restate something already said or already "
                     "returned by a tool in this conversation; summary = write up what was already "
                     "established; draft = compose text; pasted_text = work out what a message or "
                     "thread pasted in THIS turn says; action = asks to file or create something."))
    answer_quote: str = Field(
        default="",
        description=("For recall ONLY: a short verbatim quote from this conversation — a user message or "
                     "a tool result, never an assistant answer — that contains the answer. Code checks it.")) 
    relevant_facts: list[str] = Field(
        default_factory=list,
        description="Values from earlier turns this answer needs (ids, dates, numbers) — the value itself.")
    relevant_constraints: list[str] = Field(
        default_factory=list, description="Rules the user stated that are still in force.")
    action_requested: bool = Field(
        default=False,
        description=("True only if THIS message asks to create or file a record ('go ahead', "
                     "'file it'). Drafting or writing text is NOT a request to file."))

    @property
    def requires_tools(self) -> bool:
        """Derived by code, not chosen by the model: only a lookup gathers evidence."""
        return self.request_type == "lookup"


def unverified_employee_id(args: dict, caller_id: str, known_text: str) -> str | None:
    """An `employee_id` argument must be the caller's own, or appear in a tool result or the
    user's words. Measured: the model guessed 'Rachel Stein (E002)' — the real id is E010 —
    and reported she had no ticket (docs/OBSTACLES.md #10). Returns the offending id."""
    emp = args.get("employee_id")
    if emp and (not re.fullmatch(r"E\d{3}", emp) or (emp != caller_id and emp not in known_text)):
        return emp      # a name passed as an id, or an id nobody established
    return None


FRESHNESS = re.compile(r"\b(right now|now|currently|still|after that|at the moment|today|latest)\b", re.I)


_BRACKET = re.compile(r"\[[^\]]*\]")


def _norm(text: str) -> str:
    """Compare words, not formatting. Tool results arrive as JSON text, where a line break is
    the two characters backslash-n and a dash may be \\u2014; unescape those first, or no quote
    spanning a wrapped line can ever match (docs/OBSTACLES.md #16)."""
    text = re.sub(r"\\u[0-9a-fA-F]{4}", " ", text.replace("\\n", " ").replace("\\t", " "))
    return re.sub(r"\W+", " ", text).lower().strip()


def verify_request_type(plan: TurnPlan, newest_message: str, grounding_text: str) -> TurnPlan:
    """Make the planner's no-lookup claims CHECKABLE (docs/OBSTACLES.md #13). A model's label
    can always be wrong, so code verifies it:
      recall       needs a verbatim quote that really exists in the user's messages or tool
                   results, and the question must not ask for the current state;
      pasted_text  the message must actually contain pasted text (several lines).
    Anything that fails verification becomes a lookup. summary / draft / action stand."""
    kind = plan.request_type
    if kind == "recall":
        # A citation the planner copied along with the words is not part of the quote (#17).
        # Several facts arrive as one excerpt per line; each line must be verbatim (#18).
        excerpts = [_norm(line) for line in _BRACKET.sub(" ", plan.answer_quote).splitlines()]
        excerpts = [e for e in excerpts if e]
        ground = _norm(grounding_text)
        if (FRESHNESS.search(newest_message) or sum(map(len, excerpts)) < 6
                or not all(e in ground for e in excerpts)):
            kind = "lookup"
    elif kind == "pasted_text" and newest_message.count("\n") < 3:
        kind = "lookup"
    return plan if kind == plan.request_type else plan.model_copy(update={"request_type": kind})


def enforce_evidence(plan: TurnPlan, has_evidence: bool) -> TurnPlan:
    """Deterministic override of the planner: with no tool result anywhere in the
    conversation yet, a lookup is REQUIRED. Measured: on a first-turn policy question the
    planner skipped tools and the model answered from nothing, with invented citations
    (docs/OBSTACLES.md #5)."""
    if has_evidence or plan.requires_tools or plan.action_requested:
        return plan
    return plan.model_copy(update={"request_type": "lookup"})


def select_tools(plan: TurnPlan, all_read_tools: list[str]) -> list[str]:
    """Intent -> visible READ tools. Plain code: reviewable, testable, identical every run."""
    if not plan.requires_tools:
        return []
    chosen = LOADOUTS.get(plan.current_intent)
    # Only tools the server actually serves: a missing one is dropped, not a crash.
    return sorted(all_read_tools) if chosen is None else [n for n in chosen if n in all_read_tools]


CITE_REMINDER = (
    "\n\nYOUR PREVIOUS DRAFT CITED NOTHING, OR CITED A RECORD NO TOOL RETURNED. Every fact you state from a tool result must carry its "
    "citation: copy the record's `cite` value (e.g. [record: OT005]) or the document's "
    "[documents/... § section] exactly as the tool returned it.")


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
    "- request_type examples (illustrative wording):\n"
    "    lookup      'Is the VPN article still current?' / 'Does a contractor need MFA?' / 'What is open now?'\n"
    "    recall      'Remind me what date I mentioned.' / 'Who owns the policy you just read?' / "
    "'So does that need sign-off?' (answered by a policy already returned above)\n"
    "    summary     'Write up where this stands for my manager.'\n"
    "    draft       'Turn that into two lines I can paste.' / 'Draft one sentence explaining why.'\n"
    "    pasted_text a forwarded email or thread pasted into this message, asking what it means or what applies\n"
    "    action      'Go ahead and file it.'\n"
    "- For recall you MUST give answer_quote: a short verbatim quote from a user message, a tool "
    "result or the session memory that contains the answer — copied character for character, never "
    "reworded. Several facts: one exact excerpt per line. If you cannot quote it, it is a lookup.\n"
    "- request_type decides whether evidence is gathered. Use lookup unless the user clearly asks to "
    "recall/restate, summarise, draft, or read a message pasted in this turn. A new topic, a rule, "
    "threshold, owner or date no tool result here states, or 'what is it now / after that' is a lookup. "
    "A user's mention of a rule is not its content.\n"
    "- A DIFFERENT TOPIC needs a different document or record: having looked up the laptop does not "
    "answer a question about monitors.\n"
    "- action_requested only when this message asks to file or create something (request_type action).\n"
    "- You get distilled session memory plus the raw conversation since it was written. "
    "Memory is history, not this turn. Checklists, seat counts, tickets and inventory in memory "
    "are a SNAPSHOT: if the user asks what the state is NOW, it is a lookup."
)

ANSWER_PROMPT = (
    "You are the NovaOps internal assistant. Today is {today}.\n"
    "The person asking is employee {caller_id} ({caller_group}). 'I', 'me' and 'my' mean "
    "{caller_id}: use that id directly in tool calls and never ask the user for it.\n"
    "- Answer ONLY from tool results in this conversation. If you have none for a claim, call a "
    "tool; if no tool can answer, say what is missing. Never invent a person, an id, a number, a "
    "policy rule, a record or a document.\n"
    "- Never guess another person's employee id: look them up with get_employee first.\n"
    "- CITE after every claim by copying the `cite` value of the tool result it came from, e.g. "
    "[record: OT005] or [documents/policies/equipment_policy.md § Personal laptops]. Never write a "
    "citation that no tool returned.\n"
    "- Whether an approval is needed: state the threshold the governing source gives, with its "
    "number, and compare it to the amount in the records.\n"
    "- Dates as the source states them: when something takes effect, not only the month it is proposed.\n"
    "- Be specific: give the exact ids, dates, amounts and statuses the tools returned. When you "
    "identify a person, give their name AND employee id (first names collide).\n"
    "- A status summary for a joiner states name, employee id, start date and location, then each "
    "item with its status and cause as the records give it.\n"
    "- A constraint the user mentioned (e.g. a spending freeze) is a rule to apply, not evidence of "
    "why something is blocked. State causes only as the records give them.\n"
    "- If two sources disagree, the newer or more specific one governs — say which and why.\n"
    "- When the user pastes a message or thread and asks what applies to them, answer from that text, "
    "list ONLY the items that are theirs, and cite it as (forwarded thread). Do not name, list or "
    "summarise anyone else's items — not even in an 'everything else is handled by…' sentence.\n"
    "- Never say an action was taken unless a tool result shows it.\n"    "- If a tool says something is NOT recorded (e.g. which employee holds a seat), say it is not "
    "recorded and report what is. Never infer it from something else: role entitlement is not a seat.\n"
    "- Never say access was granted or is active. Filing and approving are done by the approval "
    "workflow, not by you.\n"
    "- If the user explicitly asks what the manager playbook or manager's guide says and no tool "
    "returned it, say it is available to people managers only. Do not reconstruct it from other sources.\n"
    "- Answer the current request in at most six sentences unless asked for more (a summary may be longer)."
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


def planner_messages(messages: list, memory_text: str, distilled_upto: int) -> list:
    """Bounded planner context (Lesson 10 stage 3): memory + only the fresh messages."""
    fresh = render_transcript(messages[distilled_upto:-1]) or "(nothing new)"
    return [SystemMessage(PLANNER_PROMPT),
            HumanMessage(f"Session memory:\n{memory_text}\n\nConversation since then:\n{fresh}\n\n"
                         f"Newest message:\n{messages[-1].content}")]


def render_plan(plan: TurnPlan, memory_text: str = "") -> str:
    def bullets(items):
        return "\n".join(f"  - {i}" for i in items) if items else "  - (none)"
    return ("\n\n--- CONTEXT FOR THIS TURN ---\n"
            f"Current intent: {plan.current_intent}\n"
            f"Established facts:\n{bullets(plan.relevant_facts)}\n"
            "Rules the USER stated (instructions to follow — NOT facts, and never the cause of a "
            f"blocked item):\n{bullets(plan.relevant_constraints)}\n"
            + (f"Session memory:\n{memory_text}\n" if memory_text else "")
            + "--- END CONTEXT ---")
