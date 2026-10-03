"""Shared test doubles: a role-aware scripted agent team, fake Jev and a frozen-evidence decider.

No network, no credentials. These never produce scores or decisions shown to users; they only drive
the real orchestration code paths.
"""

import json

from evidencetrail import team
from evidencetrail.gemini import ModelTurn
from evidencetrail.jev import ProviderUnavailable
from evidencetrail.scenarios import get_case
from evidencetrail.tools import FINISH


class FakeJev:
    def __init__(self, fail=False, triage=None):
        self.fail = fail
        self.states = []
        self.triage_states = []
        self.triage = triage or {"suspicion": "NOT_SUSPICIOUS", "severity": 0}

    def assess(self, state, questions=None):
        if questions is not None and "suspicion" in questions:  # alert triage call
            self.triage_states.append(state)
            if self.fail:
                raise ProviderUnavailable("fake outage")
            return {"raw": {"answers": {"suspicion": {"type": "choice", "choice": self.triage["suspicion"]}}},
                    "normalized": dict(self.triage), "model": "jev-fake-1", "usage": None}
        self.states.append(state)
        if self.fail:
            raise ProviderUnavailable("fake outage")
        return {"raw": {"answers": {"recipient_risk": {"type": "choice", "choice": "HIGH",
                                                       "confidence": 0.7, "probabilities": {"HIGH": 0.7}}}},
                "normalized": {"recipient_risk": "HIGH"}, "model": "jev-fake-1", "usage": None}


class VaryingJev(FakeJev):
    """Alternates its answers so repeated-call summaries have something to summarise."""

    def assess(self, state, questions=None):
        self.states.append(state)
        risk = "HIGH" if len(self.states) % 2 else "ELEVATED"
        return {"raw": {"answers": {}}, "normalized": {"recipient_risk": risk, "manipulation_indicators": 0.5},
                "model": "jev-fake-1", "usage": None}


def results(steps):
    out = []
    for s in steps:
        if s.get("type") == "function_result":
            out.append((s["name"], json.loads(s["result"][0]["text"])))
    return out


def turn(name, args, call_id):
    call = {"id": call_id, "name": name, "arguments": args}
    return ModelTurn([{"type": "function_call", **call}], [call], "", "scripted-team-1", None)


class AutoTeam:
    """Role-aware scripted model. The role is inferred from the registered tool declarations.

    order            specialists the orchestrator consults, in order (None = all available; [] = none)
    claims_override  replace the orchestrator's finish claims (e.g. to cite invented evidence IDs)
    specialist_hook  hook(role, plan, transaction) -> plan, to script unusual specialist tool calls
    """
    provider = "scripted"
    requested_model = "scripted-team"

    def __init__(self, action="ALLOW", order=None, extra_orch_calls=(), specialist_hook=None, fail_role=None,
                 no_report_roles=(), bad_ids_role=None, claims_override=None):
        self.action, self.order = action, order
        self.extra_orch_calls = list(extra_orch_calls)
        self.specialist_hook = specialist_hook
        self.fail_role, self.no_report_roles, self.bad_ids_role = fail_role, set(no_report_roles), bad_ids_role
        self.claims_override = claims_override
        self.seen, self.turns = [], 0

    def _role(self, names):
        if team.CONSULT in names:
            return "orchestrator"
        for role, spec in team.SPECIALISTS.items():
            if set(spec["tools"]) & names:
                return role

    def generate(self, system, steps, tools):
        self.turns += 1
        names = {t["name"] for t in tools}
        role = self._role(names)
        self.seen.append((role, system, steps, tools))
        if role == self.fail_role:
            raise ProviderUnavailable("fake outage")
        res = results(steps)
        if role == "orchestrator":
            return self._orchestrate(tools, steps, res)
        return self._specialist(role, steps, res)

    def _orchestrate(self, tools, steps, res):
        if self.extra_orch_calls:
            name, args = self.extra_orch_calls.pop(0)
            return turn(name, args, f"o{len(res)}x")
        available = next(t for t in tools if t["name"] == team.CONSULT)["parameters"]["properties"]["specialist"]["enum"]
        wanted = ["behavior_device", "recipient_network", "risk_judge"] if self.order is None else self.order
        order = [r for r in wanted if r in available]
        done = [r for r in res if r[0] == team.CONSULT and "error" not in r[1]]
        if len(done) < len(order):
            return turn(team.CONSULT, {"specialist": order[len(done)], "question": f"Please assess via {order[len(done)]}."},
                        f"o{len(res)}")
        ids = [e["evidence_id"] for _, r in done for e in r["new_evidence"] if e["type"] not in ("jev_assessment", "tool_error")]
        claims = self.claims_override if self.claims_override is not None else [
            {"text": "Specialist evidence reviewed.", "supporting_evidence_ids": ids[:3]}]
        return turn(FINISH, {"recommended_action": self.action, "status": "COMPLETE", "claims": claims,
                             "remaining_uncertainty": "none material"}, "ofin")

    def _specialist(self, role, steps, res):
        opening = json.loads(steps[0]["content"])
        tx = opening["transaction"]
        plans = {
            "behavior_device": [("get_behavior_profile", {"customer_id": tx["customer_id"]}),
                                ("inspect_device", {"transaction_id": tx["transaction_id"]})],
            "recipient_network": [("inspect_recipient", {"recipient_id": tx["recipient_id"]}),
                                  ("search_relationship_graph", {"recipient_id": tx["recipient_id"], "max_hops": 2})],
            "risk_judge": [("assess_with_jev", {"evidence_ids": [e["evidence_id"] for e in opening.get("available_evidence", [])]})],
        }
        plan = list(plans[role])
        if self.specialist_hook:
            plan = self.specialist_hook(role, plan, tx)
        done = [r for r in res if r[0] != team.REPORT]
        if len(done) < len(plan):
            name, args = plan[len(done)]
            return turn(name, args, f"{role}{len(res)}")
        if role in self.no_report_roles:
            return ModelTurn([], [], "I am done.", "scripted-team-1", None)
        ids = [r["evidence_id"] for _, r in done if "evidence_id" in r]
        if role == self.bad_ids_role:
            ids = ids + ["EV-999"]
        return turn(team.REPORT, {"summary": f"{role} finished", "remaining_uncertainty": "none",
                                  "findings": [{"text": f"{role} evidence collected", "supporting_evidence_ids": ids}]},
                    f"{role}rep")


class FrozenDecider:
    """Decision model for the fixed-evidence experiment: cites every evidence ID in the frozen bundle."""
    provider = "scripted"
    requested_model = "frozen-decider"

    def __init__(self, actions=("REVIEW",), fail_at=()):
        self.actions, self.fail_at, self.calls, self.seen = list(actions), set(fail_at), 0, []

    def generate(self, system, steps, tools):
        self.seen.append((steps, tools))
        i = self.calls
        self.calls += 1
        if i in self.fail_at:
            raise ProviderUnavailable("fake outage")
        bundle = json.loads(steps[0]["content"])["evidence"]
        args = {"recommended_action": self.actions[i % len(self.actions)], "status": "COMPLETE",
                "claims": [{"text": "Frozen bundle reviewed.",
                            "supporting_evidence_ids": [e["evidence_id"] for e in bundle]}],
                "remaining_uncertainty": "none"}
        return turn(FINISH, args, f"f{i}")


def run_team(case_id, model=None, jev=None, enable_jev=True, triage=False, **kw):
    """Run one investigation with the scripted team. Returns (case, model, result)."""
    case = get_case(case_id)
    model = model or AutoTeam(**kw)
    r = team.investigate_team(case, model, jev or FakeJev(), "run-team", enable_jev=enable_jev, triage=triage)
    return case, model, r
