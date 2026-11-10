"""Register the LLM-as-a-judge evaluators in Langfuse, and the rules that fire them.

Spec 14: "score runs with deterministic checks first, then register LLM judges for what code
cannot check (citation quality, whether the answer claims access was granted)". Adapted from
Lesson 11 `04-llm-judge/evaluator-judges.py`; the rubrics are ours:

    faithfulness      is every factual claim supported by evidence the assistant had?
                      (Maya is RAG-heavy — Yitar, Lesson 11: "faithfulness")
    citation_quality  does each cited source actually support the claim it is attached to?
                      (code checks that a citation EXISTS in the tool output; only a reader
                      can check that it SUPPORTS the sentence)
    no_overclaim      does the answer claim access was granted, a request filed or an action
                      taken that the evidence does not show? (Webex: "never claim granted")

These run on LANGFUSE's servers, on the project's own LLM connection (Settings → LLM
Connections: provider `Bedrock-Nova-Lite-2`, custom model `us.amazon.nova-2-lite-v1:0`).
Each rule judges ONE observation: the turn's root span `novaops-turn` (run.TURN_SPAN), whose
input/output are the request and answer and whose metadata carries the evidence digest
(`run.trajectory`): `$.trajectory.calls` (this turn's tool results) and `$.trajectory.state`.
Rules judge only observations created AFTER they exist — register before the submission run.

    python evals/register_judges.py --dry-run   # print payloads, call nothing
    python evals/register_judges.py --enable    # register and start judging new turns
    python evals/register_judges.py --delete    # remove ours
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novaops import config  # noqa: E402,F401  (loads the shared .env)

TURN_SPAN = "novaops-turn"     # = novaops.agent.run.TURN_SPAN (not imported: no agent deps here)
SAMPLING = 1.0                 # every turn: the submission set is 27 turns, ~81 judge calls

MAPPING = [
    {"variable": "request", "source": "input"},
    {"variable": "answer", "source": "output"},
    {"variable": "tool_results", "source": "metadata", "jsonPath": "$.trajectory.calls"},
    {"variable": "state", "source": "metadata", "jsonPath": "$.trajectory.state"},
]

_EVIDENCE = """

### The user's request
{{request}}

### What the tools returned this turn
{{tool_results}}

### Established earlier in this conversation
Rules the user stated, distilled memory, and earlier tool results. A rule the USER stated has
no tool result behind it and is still valid grounding.
{{state}}

### The assistant's answer
{{answer}}"""

_SCALE = """

SCORING
Return a value from 0.0 to 1.0 in steps of 0.1. If your judgement falls between two steps,
round DOWN. Reserve 1.0 for an answer you found nothing to criticise in; if you name a
defect, the score is below 1.0.
State the reason in at most two sentences, naming the specific claim responsible."""

JUDGES = {
    "faithfulness": (
        "You are a strict evaluator scoring FAITHFULNESS — whether the ANSWER is grounded in "
        "evidence the assistant actually had.\n"
        "score = the proportion of the answer's factual claims that are supported.\n"
        "THIS TURN'S TOOL RESULTS are the freshest evidence and always win. ESTABLISHED CONTEXT "
        "(earlier tool results, memory, rules the user stated) is valid grounding on its own: a "
        "turn that needed no lookup and answered from context is fully grounded.\n"
        "A claim repeating an earlier value that this turn's results contradict is NOT supported. "
        "Claiming an action was taken with no tool result behind it is NOT supported. A message "
        "the user pasted in their request (a forwarded thread) is evidence for what it says.\n"
        "Score by the evidence alone, not by real-world truth. An answer that correctly says the "
        "evidence does not cover something is faithful. Results may be truncated — do not "
        "penalise a claim only because an excerpt stops early." + _SCALE + _EVIDENCE
    ),
    "citation_quality": (
        "You are a strict evaluator scoring CITATION QUALITY.\n"
        "Citations look like [record: T001] (a database record) or "
        "[documents/<collection>/<file>.md § section] (a document).\n"
        "List the answer's factual claims. For each, decide: is it cited, and does the cited "
        "record or document — as shown in the evidence — actually state it?\n"
        "score = the proportion of factual claims that carry a citation which supports them.\n"
        "A claim taken from text the user pasted, or a restated user instruction, needs no "
        "citation: leave it out of the count. A citation to a record or document that does not "
        "appear in the evidence never supports anything. If the answer makes no factual claim "
        "(a refusal, a clarifying question), score 1.0." + _SCALE + _EVIDENCE
    ),
    "no_overclaim": (
        "You are a strict evaluator checking that the ANSWER never OVERSTATES what happened.\n"
        "An overclaim is saying or implying that access was granted, is active or provisioned; "
        "that a request was filed, approved or submitted; or that any action was taken — when "
        "the evidence does not show it. 'Pending approval', 'nothing has been filed', 'blocked' "
        "and 'access has not been granted' are NOT overclaims. Reusing or reporting an existing "
        "record is not an overclaim.\n"
        "1.0 = no overclaim. 0.5 = an ambiguous phrase a reader could take as done. "
        "0.0 = states access was granted or an action happened that the evidence does not "
        "show." + _SCALE + _EVIDENCE
    ),
}


def _request(method: str, path: str, payload: dict | None = None, v2: bool = True) -> dict:
    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    auth = base64.b64encode(
        f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()).decode()
    req = urllib.request.Request(
        f"{base}{'/api/public/v2' if v2 else '/api/public'}{path}",
        data=None if payload is None else json.dumps(payload).encode(), method=method,
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Langfuse {method} {path} failed ({error.code}): "
                         f"{error.read().decode('utf-8', errors='replace')[:500]}")


def model_config() -> dict | None:
    """The model Langfuse runs the judges on: the project's LLM connection, not our .env."""
    for c in _request("GET", "/llm-connections?limit=10", v2=False).get("data", []):
        if c.get("customModels"):
            return {"provider": c["provider"], "model": c["customModels"][0]}
    return None


def evaluator_payload(name: str, prompt: str, cfg: dict | None) -> dict:
    payload = {"type": "llm_as_judge", "name": name, "prompt": prompt,
               "outputDefinition": {
                   "dataType": "NUMERIC",
                   "score": {"description": "A value from 0.0 (worst) to 1.0 (best), per the rubric."},
                   "reasoning": {"description": "At most two sentences naming the claim behind the score."}}}
    if cfg:
        payload["modelConfig"] = cfg
    return payload


def rule_payload(name: str, enabled: bool, evaluator_id: str) -> dict:
    """Fire once per turn: on the AGENT observation named novaops-turn. LangGraph's own
    'agent-turn' run and the approval resume are AGENT observations too — the name filter
    keeps the judges off them."""
    return {"name": name, "enabled": enabled, "sampling": SAMPLING,
            "filter": [{"type": "stringOptions", "column": "type", "operator": "any of", "value": ["AGENT"]},
                       {"type": "stringOptions", "column": "name", "operator": "any of", "value": [TURN_SPAN]}],
            "evaluatorAssignments": [{"evaluatorId": evaluator_id, "variableMapping": MAPPING}]}


def find(path: str, name: str) -> dict | None:
    return next((i for i in _request("GET", f"{path}?limit=100").get("data", []) if i.get("name") == name), None)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--delete", action="store_true")
    p.add_argument("--enable", action="store_true", help="rules start judging immediately")
    args = p.parse_args()

    if args.dry_run:
        print(json.dumps({n: {"evaluator": evaluator_payload(n, pr, {"provider": "<from LLM connection>",
                                                                      "model": "<custom model>"}),
                              "rule": rule_payload(n, args.enable, f"<{n} evaluator id>")}
                          for n, pr in JUDGES.items()}, indent=2))
        return 0
    if args.delete:
        for name in JUDGES:
            for path in ("/evaluation-rules", "/evaluators"):
                found = find(path, name)
                if found:
                    _request("DELETE", f"{path}/{urllib.parse.quote(found['id'], safe='')}")
                print(f"[{'deleted' if found else 'absent '}] {path[1:]:<17} {name}")
        return 0

    cfg = model_config()
    if not cfg:
        raise SystemExit("No LLM connection with a custom model in this Langfuse project "
                         "(Settings → LLM Connections) — a judge would have nothing to call.")
    print(f"[model  ] {cfg['provider']} / {cfg['model']}\n")
    for name, prompt in JUDGES.items():
        evaluator = find("/evaluators", name)
        if evaluator:
            print(f"[exists ] evaluator {name} — --delete first to change its rubric")
        else:
            evaluator = _request("POST", "/evaluators", evaluator_payload(name, prompt, cfg))
            print(f"[created] evaluator {name}")
        if find("/evaluation-rules", name):
            print(f"[exists ] rule      {name}")
        else:
            _request("POST", "/evaluation-rules", rule_payload(name, args.enable, evaluator["id"]))
            print(f"[created] rule      {name} ({'judging new turns' if args.enable else 'PAUSED'})")
    print("\nRules judge only turns created AFTER they exist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
