"""Typed return contracts (spec 6.5) and the deterministic checks on them.

  AccessRequestIntent  the Maya -> Webex handoff: Maya proposes, she never files.
  OnboardingChecklist  items, each with a status and >= 1 citation; blocked items carry
                       the reason; an overall status.
  citation_report      every source an answer cites must have come back from a tool.

The model may PROPOSE these objects; application code validates them before anything is
returned. A model's word that it complied is not checked evidence.
"""
import re
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["completed", "blocked", "pending", "needs_human", "failed"]

_DOC = re.compile(r"documents/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-.]+\.md")
_BRACKET = re.compile(r"\[([^\]]+)\]")
_ID = re.compile(r"\b[A-Z]{1,3}\d{3}\b")


# --- the Maya -> Webex handoff ------------------------------------------------

class AccessRequestProposal(BaseModel):
    """What the MODEL extracts from the conversation."""
    subject_employee_id: str = Field(description="Employee id the access is FOR, e.g. E001.")
    subject_name: str = Field(description="That employee's full name.")
    system: str = Field(description="The system requested, e.g. Webex.")
    justification: str = Field(description="One-sentence business justification.")


class AccessRequestIntent(AccessRequestProposal):
    """The handoff the Webex scope consumes (spec 6.5). Application code adds identity,
    traceability and state — never the model."""
    requested_by: str
    source_thread_id: str
    request_id: str
    status: Literal["pending_approval"] = "pending_approval"


def handoff_answer(intent: AccessRequestIntent) -> str:
    """Deterministic: what was proposed, what was NOT done. No model writes this text."""
    # Judges read "handed it to IT operations" as an action no tool showed, and "nothing has
    # been filed" as contradicting the approval request filed below it (#39): say exactly
    # which record exists and which does not.
    return (f"I've passed a {intent.system} access request for {intent.subject_name} "
            f"({intent.subject_employee_id}) to the IT approval workflow; its result is below. "
            f"Status: pending approval. No access request has been filed and access has not been "
            f"granted. Proposed justification (a draft for the approver, not a recorded fact): "
            f"{intent.justification}")


# --- the onboarding checklist -------------------------------------------------

class ChecklistItem(BaseModel):
    item: str = Field(description="A required system, piece of equipment, task or policy acknowledgement.")
    category: Literal["system", "equipment", "task", "policy"]
    status: Literal["done", "pending", "planned", "blocked", "unknown"]
    citations: list[str] = Field(
        description="At least one: a document path 'documents/<collection>/<file>.md' or a record id like OT005.")
    blocked_reason: str | None = Field(default=None, description="Required when status is blocked.")


class ChecklistProposal(BaseModel):
    employee_id: str
    employee_name: str
    start_date: str | None = None
    items: list[ChecklistItem]


class OnboardingChecklist(ChecklistProposal):
    status: Status
    validation_errors: list[str] = Field(default_factory=list)


def checklist_errors(proposal: ChecklistProposal, evidence: str) -> list[str]:
    """Every item needs >= 1 citation that actually appears in the tool evidence, and a
    blocked item needs its reason."""
    errors = []
    if not proposal.items:
        errors.append("checklist has no items")
    for it in proposal.items:
        if not it.citations:
            errors.append(f"{it.item}: no citation")
        for c in it.citations:
            key = c.strip("[] ").removeprefix("record:").strip().split(" §")[0]
            if key not in evidence:
                errors.append(f"{it.item}: citation {c!r} is not in any tool result")
        if it.status == "blocked" and not it.blocked_reason:
            errors.append(f"{it.item}: blocked without a reason")
    return errors


# --- citations ----------------------------------------------------------------

def sources_in(text: str) -> set[str]:
    """Document paths that appear in tool output (what the model was actually given)."""
    return set(_DOC.findall(text))


def attach_sources(answer: str, turn_evidence: str) -> str:
    """Last resort after one rewrite (#19): the application, not the model, attaches the
    sources an uncited answer rests on — the record ids it names that a tool returned this
    turn, else the documents this turn's tools returned. Nothing is attached that no tool
    returned, and an answer that already cites is left alone."""
    if citation_report(answer, turn_evidence)["has_citation"]:
        return answer
    named = sorted({i for i in _ID.findall(answer) if i in turn_evidence})
    cites = [f"[record: {i}]" for i in named] or [f"[{d}]" for d in sorted(sources_in(turn_evidence))[:3]]
    return f"{answer}\n\nSources: {' '.join(cites)}" if cites else answer


def citation_report(answer: str, evidence: str) -> dict:
    """Which documents/records the answer cites, and whether any did not come from a tool.
    A citation is any [bracket] holding a document path or a record id — the form may vary
    ([record: OT005], [cite: documents/...md], [OT005]); a bracket with neither
    ('[cite: employee record]') is not a citation. An invented citation is worse than none:
    it looks checkable and is not."""
    docs, records = set(), set()
    for inside in _BRACKET.findall(answer):
        found = _DOC.findall(inside)
        docs.update(found)
        if not found:
            records.update(_ID.findall(inside))
    return {
        "cited_documents": sorted(docs),
        "cited_records": sorted(records),
        "has_citation": bool(docs or records),
        "unsupported": sorted([d for d in docs if d not in evidence] +
                              [r for r in records if r not in evidence]),
    }


# --- the Webex decision ---------------------------------------------------------

Decision = Literal["pending_approval", "rejected", "request_on_file", "not_eligible"]
_GRANTED = re.compile(r"\b(?<!not been )(?<!not )(?<!never )granted\b|\baccess (is|was) (now )?(active|provisioned|enabled)\b", re.I)


class AccessDecision(BaseModel):
    """Spec 6.5: observed facts, actions actually taken and recommended next steps, kept
    apart; the blocking reason; the status. Built by application code from records — a
    model never writes it — and it never states that access was granted."""
    subject_employee_id: str
    system: str
    decision: Decision
    observed_facts: list[str]
    actions_taken: list[str]
    next_steps: list[str]
    blocking_reason: str | None = None
    status: Status
    approval_id: str | None = None
    access_request_id: str | None = None
    source_thread_id: str
    request_id: str


def claims_granted(text: str) -> bool:
    return bool(_GRANTED.search(text))


def decision_answer(d: AccessDecision) -> str:
    """Deterministic text for the AccessDecision. Asserted never to claim a grant."""
    lines = [f"{d.system} access for {d.subject_employee_id}: {d.decision.replace('_', ' ')} (status: {d.status}). "
             "Access has not been granted."]
    if d.blocking_reason:
        lines.append(f"Blocked by: {d.blocking_reason}")
    lines += ["Observed:", *[f"- {f}" for f in d.observed_facts]]
    lines += ["Actions taken:", *([f"- {a}" for a in d.actions_taken] or ["- none"])]
    lines += ["Next steps:", *[f"- {s}" for s in d.next_steps]]
    text = "\n".join(lines)
    assert not claims_granted(text), text
    return text


_OTHERS = re.compile(r"\n\s*(everything else|all other|the rest|other items|anything else|the remaining)\b[^\n]*", re.I)


def only_theirs(answer: str) -> str:
    """Pasted-thread turns (S9 t2): the caller asked what is THEIRS. A closing line about who
    owns everything else leaks other people's items (forbidden facts) — measured four times
    despite the prompt rule, so code removes it (docs/OBSTACLES.md #25)."""
    return _OTHERS.sub("", answer).rstrip()
