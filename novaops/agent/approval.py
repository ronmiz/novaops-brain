"""The approval workflow — Webex consumes the AccessRequestIntent (Milestone 4).

    START -> gather -> wait --(approved)--> release -> decide -> END
                        |  ^ (still open: pause again)       ^
                        |  +---------+                       |
                        +--(rejected / not eligible)---------+

  gather   reads the records (subscription, existing requests + approvals, tickets,
           entitlement) and files the approval request — REUSING an open one (AP001)
  wait     interrupt(): the run stops here and the SQLite checkpointer keeps it, so it
           survives the process dying. On resume it re-reads the approval ROW; the resume
           payload is ignored — what a caller says is not an approval, a record is
  release  write_gate.released_writes(approval row) -> create_access_request, idempotent
  decide   AccessDecision built from records by code; never claims access was granted

No model call anywhere in this graph. One thread per (employee, system), so a replay of the
same request finds the same paused run instead of starting a second one.
"""
import json
from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import contracts, write_gate

Call = Callable[[str, dict], Awaitable[Any]]
OPEN = ("needed", "pending")
# Amir Haddad, IT Manager — the approver the seed names on access approvals (AP001, AP004).
IT_APPROVER = "E006"


class ApprovalState(TypedDict, total=False):
    intent: dict             # AccessRequestIntent
    trace_id: str | None     # the conversational turn's trace — a resume reports into it
    facts: dict
    approval: dict | None
    written: dict | None


def thread_for(subject_employee_id: str, system: str) -> str:
    return f"approval-{subject_employee_id}-{system.lower()}"


def mcp_caller(by_name: dict, log: list | None = None) -> Call:
    """Call an MCP tool from application code and return its JSON value. `log` collects the
    tool names, so the turn's result reports every tool that ran — not only the model's."""
    async def call(name: str, args: dict) -> Any:
        if log is not None:
            log.append(name)
        msg = await by_name[name].ainvoke({"name": name, "args": args, "id": f"app-{name}", "type": "tool_call"})
        structured = (getattr(msg, "artifact", None) or {}).get("structured_content")
        if structured is not None:
            return structured.get("result", structured) if set(structured) == {"result"} else structured
        blocks = msg.content if isinstance(msg.content, list) else [msg.content]
        values = [json.loads(b["text"] if isinstance(b, dict) else b) for b in blocks if b]
        return values[0] if len(values) == 1 else values
    return call


def _open_request(facts: dict) -> dict | None:
    return next((r for r in facts["requests"] if r["system_name"].lower() == facts["system"].lower()
                 and r["status"] not in ("rejected", "closed", "cancelled")), None)


def build_approval_graph(call: Call, checkpointer=None, callbacks: list | None = None):

    async def gather(state: ApprovalState) -> dict:
        intent = state["intent"]
        who, system = intent["subject_employee_id"], intent["system"]
        employee = (await call("get_employee", {"query": who}) or [{}])[0]
        facts = {
            "system": system,
            "employee": employee,
            "entitled": system.lower() in str(employee.get("systems_allowed_by_role", "")).lower(),
            "subscription": next(iter(await call("check_software_subscription", {"software": system}) or []), None),
            "requests": await call("list_access_requests", {"employee_id": who}) or [],
            "tickets": await call("list_employee_tickets", {"employee_id": who}) or [],
        }
        if not facts["entitled"]:
            return {"facts": facts, "approval": None}
        existing = _open_request(facts)
        if existing:      # reuse AR001 and the approval already waiting on it
            prior = next((a for a in existing["approvals"]
                          if a["request_type"] == "access_request" and a["status"] in OPEN), None)
            kind, ref, approver = "access_request", existing["request_id"], (prior or {}).get("approver_id", IT_APPROVER)
        else:
            kind, ref, approver = "access_request_intent", f"{who}:{system}", IT_APPROVER
        approval = await call("request_approval", {
            "request_type": kind, "request_id": ref, "approver_id": approver,
            "reason": f"{system} access for {who}: {intent['justification']}"})
        return {"facts": facts, "approval": approval}

    async def wait(state: ApprovalState) -> dict:
        approval = await call("get_approval", {"approval_id": state["approval"]["approval_id"]})
        if approval["status"] in OPEN:
            interrupt({"approval_id": approval["approval_id"], "approver_id": approval["approver_id"],
                       "question": f"Approve {approval['request_type']} {approval['request_id']}?"})
            approval = await call("get_approval", {"approval_id": approval["approval_id"]})
        return {"approval": {**state["approval"], **approval}}

    def after_wait(state: ApprovalState) -> str:
        status = state["approval"]["status"]
        return "release" if status == "approved" else "wait" if status in OPEN else "decide"

    async def release(state: ApprovalState) -> dict:
        intent, approval = state["intent"], state["approval"]
        if "create_access_request" not in write_gate.released_writes(approval):
            return {"written": None}
        written = await call("create_access_request", {
            "employee_id": intent["subject_employee_id"], "system": intent["system"],
            "justification": intent["justification"], "approval_id": approval["approval_id"]})
        return {"written": written}

    def after_gather(state: ApprovalState) -> str:
        return "wait" if state.get("approval") else "decide"

    def decide(state: ApprovalState) -> dict:
        return {}            # a named step in the trace; build_decision() renders the object

    graph = StateGraph(ApprovalState)
    graph.add_node("gather", gather)
    graph.add_node("wait", wait)
    graph.add_node("release", release)
    graph.add_node("decide", decide)
    graph.add_edge(START, "gather")
    graph.add_conditional_edges("gather", after_gather, {"wait": "wait", "decide": "decide"})
    graph.add_conditional_edges("wait", after_wait, {"release": "release", "wait": "wait", "decide": "decide"})
    graph.add_edge("release", "decide")
    graph.add_edge("decide", END)
    app = graph.compile(checkpointer=checkpointer)
    # The span name a reader looks for in the trace, under the turn and under the resume.
    return app.with_config({"run_name": "approval-workflow", **({"callbacks": callbacks} if callbacks else {})})


def build_decision(values: dict) -> contracts.AccessDecision:
    """The AccessDecision for whatever point the workflow has reached — paused or finished."""
    intent, facts = values["intent"], values["facts"]
    approval, written = values.get("approval"), values.get("written")
    who, system = intent["subject_employee_id"], intent["system"]
    observed, actions, steps = [], [], []
    sub = facts.get("subscription")
    over = bool(sub and sub["active_seats"] >= sub["seat_limit"])
    if sub:
        observed.append(f"{system} has {sub['active_seats']} active seats against a {sub['seat_limit']}-seat "
                        f"limit{' — over the limit' if over else ''} [record: {sub['subscription_id']}]")
    observed.append(f"{who} is {'' if facts['entitled'] else 'NOT '}entitled to {system} by role [record: {who}]")
    for r in facts["requests"]:
        if r["system_name"].lower() == system.lower():
            observed.append(f"Access request {r['request_id']} is {r['status']}: {r['decision_reason']} "
                            f"[record: {r['request_id']}]")
            current = {(approval or {}).get("approval_id"): (approval or {}).get("status")}
            observed += [f"Approval {a['approval_id']} ({a['request_type']}) by {a['approver_id']} is "
                         f"{current.get(a['approval_id']) or a['status']} [record: {a['approval_id']}]"
                         for a in r["approvals"]]
    tickets = [t for t in facts["tickets"] if t["status"] not in ("closed", "resolved")
               and system.lower() in f"{t['subject']} {t['subcategory']}".lower()]
    observed += [f"Ticket {t['ticket_id']} '{t['subject']}' is {t['status']} [record: {t['ticket_id']}]" for t in tickets]
    if tickets:
        actions.append(f"Reused existing ticket {tickets[0]['ticket_id']} — no new ticket created")

    blocking = f"{sub['active_seats']} of {sub['seat_limit']} {system} seats are in use — no free seat" if over else None
    if not facts["entitled"]:
        decision, status = "not_eligible", "needs_human"
        blocking = f"{who}'s role is not entitled to {system}"
        steps.append(f"{who}'s manager must confirm a business need before IT can consider {system} access")
    elif approval:
        aid, approver = approval["approval_id"], approval["approver_id"]
        actions.append(f"{'Reused open approval' if approval.get('reused') else 'Filed approval request'} {aid} "
                       f"for {approver}{' — no new row' if approval.get('reused') else ''}")
        if approval["status"] in OPEN:
            decision, status = "pending_approval", "pending"
            steps.append(f"{approver} must record a decision on {aid}; nothing is filed until then")
        elif approval["status"] == "rejected":
            decision, status = "rejected", "blocked"
            blocking = f"{aid} rejected by {approver}: {approval.get('decision_reason') or 'no reason given'}"
            actions.append(f"{aid} recorded as rejected by {approver}; no access request was filed")
        else:
            decision, status = "request_on_file", "blocked" if over else "completed"
            if written:
                actions.append(f"create_access_request released against recorded approval {aid}: "
                               f"{'reused ' + written['request_id'] + ' — no new row' if written.get('reused') else 'filed ' + written['request_id']}")
    if over and status != "needs_human":
        expansion = [a for r in facts["requests"] for a in r["approvals"]
                     if a["request_type"] == "subscription_expansion" and a["status"] in OPEN]
        steps.append("Free a seat or expand the subscription"
                     + (f" — expansion needs {expansion[0]['approver_id']} ({expansion[0]['approval_id']})" if expansion else ""))
    return contracts.AccessDecision(
        subject_employee_id=who, system=system, decision=decision, observed_facts=observed,
        actions_taken=actions, next_steps=steps, blocking_reason=blocking, status=status,
        approval_id=(approval or {}).get("approval_id"),
        access_request_id=(written or {}).get("request_id") or (_open_request(facts) or {}).get("request_id"),
        source_thread_id=intent["source_thread_id"], request_id=intent["request_id"])


async def start(app, intent: dict, trace_id: str | None) -> contracts.AccessDecision:
    """Run the workflow until it pauses (or finishes) and report where it got to. Re-running
    the same request restarts the same thread from the top; every step is idempotent."""
    cfg = {"configurable": {"thread_id": thread_for(intent["subject_employee_id"], intent["system"])}}
    await app.ainvoke({"intent": intent, "trace_id": trace_id, "approval": None, "written": None}, cfg)
    return build_decision((await app.aget_state(cfg)).values)
