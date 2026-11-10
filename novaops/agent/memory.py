"""Durable conversation memory — Lesson 10 stage 3 (history distillation).

Maya's sessions are long: a constraint stated on turn 1 is needed on turn 9, and a
closed topic must stop steering tool choice. Once the fresh history crosses a threshold,
a distiller folds it into five NAMED fields; the planner then reads memory + only what
came after. Named fields, not a summary string: a summary blurs "don't file anything
until I say so" into "the user discussed filing".
"""
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

DISTIL_AFTER_MESSAGES = 12
DISTIL_AFTER_CHARS = 10_000   # ~2,500 tokens, Lesson 10's threshold


class ConversationMemory(BaseModel):
    current_intent: str = Field(description="What the session is about NOW.")
    important_facts: list[str] = Field(
        default_factory=list,
        description="Durable values later turns may need: ids, names, dates, numbers.")
    active_constraints: list[str] = Field(
        default_factory=list,
        description="Rules the user imposed that are STILL in force. Never drop one unless withdrawn.")
    decisions: list[str] = Field(
        default_factory=list, description="Conclusions reached and actions taken, including topics closed.")
    unresolved_items: list[str] = Field(
        default_factory=list, description="Open questions and outstanding work.")


DISTIL_PROMPT = (
    "You maintain the durable memory of a long support conversation. You get the memory so far "
    "and the conversation since it was last updated. Return the UPDATED memory.\n"
    "- Carry every still-relevant item forward: anything you omit is gone.\n"
    "- Keep concrete values (E001, 2026-08-01, 42 of 40 seats), not descriptions of them.\n"
    "- NEVER drop an active constraint unless the user explicitly withdrew it.\n"
    "- Move a topic the user closed into decisions and drop its raw detail.\n"
    "- Be compact."
)


def needs_distillation(messages: list, distilled_upto: int, render) -> bool:
    fresh = messages[distilled_upto:]
    return len(fresh) >= DISTIL_AFTER_MESSAGES or len(render(fresh)) >= DISTIL_AFTER_CHARS


def memory_is_safe(old: dict, new: ConversationMemory | None) -> bool:
    """Reject an empty memory, or one that silently lost an active constraint. A rejected
    memory keeps the raw history — nothing is lost (Lesson 10)."""
    if new is None or not (new.important_facts or new.decisions or new.unresolved_items):
        return False
    return len(new.active_constraints) >= len(old.get("active_constraints", []))


def render_memory(memory: dict) -> str:
    if not memory:
        return "(nothing distilled yet)"
    m = ConversationMemory(**memory)

    def bullets(items):
        return "\n".join(f"  - {i}" for i in items) if items else "  - (none)"
    return (f"Session is about: {m.current_intent}\n"
            f"Established facts:\n{bullets(m.important_facts)}\n"
            f"Constraints in force:\n{bullets(m.active_constraints)}\n"
            f"Decisions made:\n{bullets(m.decisions)}\n"
            f"Still open:\n{bullets(m.unresolved_items)}")


def distiller_messages(memory: dict, fresh_transcript: str) -> list:
    return [SystemMessage(DISTIL_PROMPT),
            HumanMessage(f"Memory so far:\n{render_memory(memory)}\n\n"
                         f"Conversation since then:\n{fresh_transcript}")]
