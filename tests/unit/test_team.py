"""Multi-agent team tests: orchestrator + specialists, shared evidence, policy, budgets, ablation."""

import json
import os
import time
import unittest

os.environ["EVIDENCETRAIL_ALERT_DB"] = ":memory:"

from evidencetrail import api, evaluator, team
from evidencetrail.alerts import AlertStore
from evidencetrail.config import MAX_CONSULTATIONS, MAX_TOOL_CALLS
from evidencetrail.gemini import ModelTurn
from evidencetrail.jev import ProviderUnavailable
from evidencetrail.metrics import summarize_runs
from evidencetrail.runs import RunManager
from evidencetrail.scenarios import get_case
from evidencetrail.tools import FINISH
from evidencetrail.trace import verify_chain
from test_evidencetrail import FakeJev

SUSPICIOUS = {"suspicion": "SUSPICIOUS", "severity": 2}


def _results(steps):
    out = []
    for s in steps:
        if s.get("type") == "function_result":
            out.append((s["name"], json.loads(s["result"][0]["text"])))
    return out


def _turn(name, args, call_id):
    call = {"id": call_id, "name": name, "arguments": args}
    return ModelTurn([{"type": "function_call", **call}], [call], "", "scripted-team-1", None)


class AutoTeam:
    """Role-aware scripted model. The role is inferred from the registered tool declarations."""
    provider = "scripted"
    requested_model = "scripted-team"

    def __init__(self, action="ALLOW", order=None, extra_orch_calls=(), specialist_hook=None,
                 fail_role=None, no_report_roles=(), bad_ids_role=None):
        self.action, self.order = action, order
        self.extra_orch_calls = list(extra_orch_calls)
        self.specialist_hook = specialist_hook
        self.fail_role, self.no_report_roles, self.bad_ids_role = fail_role, set(no_report_roles), bad_ids_role
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
        res = _results(steps)
        if role == "orchestrator":
            return self._orchestrate(tools, steps, res)
        return self._specialist(role, steps, res)

    def _orchestrate(self, tools, steps, res):
        if self.extra_orch_calls:
            name, args = self.extra_orch_calls.pop(0)
            return _turn(name, args, f"o{len(res)}x")
        available = next(t for t in tools if t["name"] == team.CONSULT)["parameters"]["properties"]["specialist"]["enum"]
        order = [r for r in (self.order or ["behavior_device", "recipient_network", "risk_judge"]) if r in available]
        done = [r for r in res if r[0] == team.CONSULT and "error" not in r[1]]
        if len(done) < len(order):
            return _turn(team.CONSULT, {"specialist": order[len(done)], "question": f"Please assess via {order[len(done)]}."},
                         f"o{len(res)}")
        ids = [e["evidence_id"] for _, r in done for e in r["new_evidence"] if e["type"] not in ("jev_assessment", "tool_error")]
        return _turn(FINISH, {"recommended_action": self.action, "status": "COMPLETE",
                              "claims": [{"text": "Specialist evidence reviewed.", "supporting_evidence_ids": ids[:3]}],
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
            return _turn(name, args, f"{role}{len(res)}")
        if role in self.no_report_roles:
            return ModelTurn([], [], "I am done.", "scripted-team-1", None)
        ids = [r["evidence_id"] for _, r in done if "evidence_id" in r]
        if role == self.bad_ids_role:
            ids = ids + ["EV-999"]
        return _turn(team.REPORT, {"summary": f"{role} finished", "remaining_uncertainty": "none",
                                   "findings": [{"text": f"{role} evidence collected", "supporting_evidence_ids": ids}]},
                     f"{role}rep")


def run_team(case_id, model=None, jev=None, enable_jev=True, triage=False, **kw):
    case = get_case(case_id)
    model = model or AutoTeam(**kw)
    r = team.investigate_team(case, model, jev or FakeJev(), "run-team", enable_jev=enable_jev, triage=triage)
    return case, model, r


class TeamFlow(unittest.TestCase):
    def test_full_team_run_reaches_the_policy_outcome_with_shared_evidence(self):
        _, _, r = run_team("case-manipulated", action="CONTEXT_CHECK")
        self.assertEqual((r["final"]["status"], r["final"]["simulated_action"]), ("COMPLETE", "CONTEXT_CHECK"))
        self.assertEqual(r["consultation_count"], 3)
        ids = [e["evidence_id"] for e in r["evidence"]]
        self.assertEqual(ids, [f"EV-{i:03d}" for i in range(1, len(ids) + 1)])  # one shared, ordered store
        self.assertEqual({e["source"] for e in r["evidence"]} - {"assess_with_jev"},
                         {"get_behavior_profile", "inspect_device", "inspect_recipient", "search_relationship_graph"})

    def test_every_trace_event_names_its_agent_and_the_chain_verifies(self):
        _, _, r = run_team("case-familiar")
        agents = {e["agent"] for e in r["events"]}
        self.assertEqual(agents, {"orchestrator", "behavior_device", "recipient_network", "risk_judge"})
        self.assertTrue(all(e["agent"] for e in r["events"]))
        self.assertTrue(verify_chain(r["events"]))
        self.assertEqual([e["agent"] for e in r["events"] if e["event_type"] == "tool_call"],
                         ["behavior_device", "behavior_device", "recipient_network", "recipient_network", "risk_judge"])

    def test_policy_still_overrides_the_orchestrator(self):
        _, _, r = run_team("case-takeover", action="ALLOW")
        self.assertEqual(r["final"]["simulated_action"], "REVIEW")
        self.assertEqual(r["final"]["rule"], "device_compromise")

    def test_header_describes_the_team(self):
        _, _, r = run_team("case-familiar")
        h = r["run_header"]
        self.assertEqual(h["architecture"], "team")
        self.assertEqual(set(h["roster"]), {"behavior_device", "recipient_network", "risk_judge"})
        self.assertEqual(h["prompt_version"], "investigator-team-prompt-v1")
        self.assertEqual(h["budgets"]["max_consultations"], MAX_CONSULTATIONS)

    def test_no_case_identity_or_label_reaches_any_agent(self):
        case, model, _ = run_team("case-manipulated", action="CONTEXT_CHECK")
        blob = json.dumps([(s, st) for _, s, st, _ in model.seen])
        for hidden in (case["case_id"], case["name"], "EXPECTED"):
            self.assertNotIn(hidden, blob)


class Boundaries(unittest.TestCase):
    def test_orchestrator_has_no_data_tools(self):
        names = [t["name"] for t in team.orchestrator_tools()]
        self.assertEqual(set(names), {team.CONSULT, FINISH})

    def test_specialists_only_see_their_own_tools(self):
        self.assertEqual({t["name"] for t in team.specialist_tools("behavior_device")},
                         {"get_behavior_profile", "inspect_device", team.REPORT})
        self.assertEqual({t["name"] for t in team.specialist_tools("risk_judge")}, {"assess_with_jev", team.REPORT})

    def test_a_specialist_cannot_call_another_specialists_tool(self):
        def hook(role, plan, tx):
            return [("inspect_recipient", {"recipient_id": tx["recipient_id"]})] if role == "behavior_device" else plan
        _, _, r = run_team("case-familiar", specialist_hook=hook)
        errs = [e for e in r["events"] if e["event_type"] == "tool_error" and e["agent"] == "behavior_device"]
        self.assertIn("not registered", errs[0]["result_snapshot"]["error"])
        self.assertFalse(any(e["type"] == "recipient_inspection" and e["evidence_id"] == errs[0]["output_evidence_ids"][0]
                             for e in r["evidence"]))

    def test_one_global_tool_budget_across_the_team(self):
        def hook(role, plan, tx):
            return [("inspect_device", {"transaction_id": tx["transaction_id"]})] * 6
        _, _, r = run_team("case-familiar", specialist_hook=hook)
        self.assertEqual(r["tool_call_count"], MAX_TOOL_CALLS)
        self.assertTrue(any(e["reason_code"] == "BUDGET_EXHAUSTED" for e in r["events"]))

    def test_consultation_budget_and_invalid_specialist_are_rejected_visibly(self):
        extra = [(team.CONSULT, {"specialist": "nobody", "question": "hi"}),
                 (team.CONSULT, {"specialist": "behavior_device", "question": ""})]
        extra += [(team.CONSULT, {"specialist": "behavior_device", "question": f"q{i}"}) for i in range(MAX_CONSULTATIONS + 1)]
        _, _, r = run_team("case-familiar", extra_orch_calls=extra)
        codes = [e["reason_code"] for e in r["events"] if e["event_type"] == "tool_error" and e["agent"] == "orchestrator"]
        self.assertEqual(codes.count("INVALID_CONSULT"), 3)  # unknown name, empty question, over budget
        self.assertEqual(r["consultation_count"], MAX_CONSULTATIONS)

    def test_orchestrator_calling_a_data_tool_directly_is_rejected(self):
        _, _, r = run_team("case-familiar", extra_orch_calls=[("inspect_device", {"transaction_id": "TX-1001"})])
        self.assertTrue(any(e["reason_code"] == "NOT_REGISTERED" for e in r["events"]))


class JevAndAblation(unittest.TestCase):
    def test_risk_judge_uses_jev_and_it_stays_a_tool(self):
        jev = FakeJev()
        _, _, r = run_team("case-manipulated", jev=jev, action="CONTEXT_CHECK")
        self.assertEqual(len(jev.states), 1)
        self.assertNotIn("case-manipulated", jev.states[0])
        ev = [e for e in r["evidence"] if e["type"] == "jev_assessment"][0]
        self.assertEqual(ev["payload"]["normalized"]["recipient_risk"], "HIGH")

    def test_no_jev_arm_drops_the_risk_judge_entirely(self):
        _, model, r = run_team("case-familiar", enable_jev=False)
        self.assertEqual(r["consultation_count"], 2)
        self.assertNotIn("risk_judge", r["run_header"]["roster"])
        self.assertEqual(r["run_header"]["arm"], "no_jev")
        enum = next(t for t in team.orchestrator_tools(False) if t["name"] == team.CONSULT)["parameters"]["properties"]["specialist"]["enum"]
        self.assertNotIn("risk_judge", enum)

    def test_consulting_an_unavailable_risk_judge_in_the_no_jev_arm_is_an_error(self):
        extra = [(team.CONSULT, {"specialist": "risk_judge", "question": "assess"})]
        _, _, r = run_team("case-familiar", enable_jev=False, extra_orch_calls=extra)
        self.assertTrue(any(e["reason_code"] == "INVALID_CONSULT" for e in r["events"]))


class Failures(unittest.TestCase):
    def test_provider_outage_inside_a_specialist_ends_the_run_honestly(self):
        _, _, r = run_team("case-familiar", fail_role="recipient_network")
        self.assertEqual((r["final"]["status"], r["final"]["simulated_action"]), ("INCOMPLETE", "REVIEW"))
        self.assertIn("unavailable", r["failure"])

    def test_orchestrator_outage_is_also_visible(self):
        _, _, r = run_team("case-familiar", fail_role="orchestrator")
        self.assertEqual(r["final"]["status"], "INCOMPLETE")

    def test_specialist_without_a_report_is_flagged_incomplete_to_the_orchestrator(self):
        _, _, r = run_team("case-familiar", no_report_roles={"recipient_network"})
        rep = [e for e in r["events"] if e["event_type"] == "specialist_report" and e["agent"] == "recipient_network"][0]
        self.assertEqual(rep["result_snapshot"]["status"], "INCOMPLETE")
        self.assertEqual(rep["reason_code"], "REPORT_INCOMPLETE")

    def test_report_citing_unknown_evidence_is_flagged(self):
        _, _, r = run_team("case-familiar", bad_ids_role="behavior_device")
        rep = [e for e in r["events"] if e["event_type"] == "specialist_report" and e["agent"] == "behavior_device"][0]
        self.assertEqual(rep["result_snapshot"]["invalid_evidence_ids"], ["EV-999"])

    def test_missing_tool_response_still_ends_incomplete_review(self):
        _, _, r = run_team("case-missing-tool")
        self.assertEqual((r["final"]["status"], r["final"]["simulated_action"]), ("INCOMPLETE", "REVIEW"))


class Integration(unittest.TestCase):
    def test_alerts_still_work_after_the_team_decides(self):
        _, _, r = run_team("case-takeover", jev=FakeJev(triage=SUSPICIOUS), triage=True)
        self.assertEqual((r["alert"]["sources"], r["alert"]["severity"]), (["jev", "policy"], "high"))
        types = [e["event_type"] for e in r["events"]]
        self.assertLess(types.index("final_decision"), types.index("alert_triage"))
        self.assertEqual({e["agent"] for e in r["events"] if e["event_type"].startswith("alert_")}, {"alert_triage"})

    def test_evaluator_trace_names_agents_and_questions(self):
        case, _, r = run_team("case-familiar")
        lines = evaluator.trace_context({"events": r["events"]})
        self.assertTrue(any("[orchestrator] consultation" in l and "question=" in l for l in lines))
        self.assertTrue(any("[recipient_network] tool_call" in l for l in lines))

    def test_manager_defaults_to_the_team_and_can_select_single(self):
        mgr = RunManager(model_factory=AutoTeam, jev_factory=FakeJev, alert_store=AlertStore(":memory:"))
        api.set_manager(mgr)
        _, body = api.handle_post("/api/investigations", {"caseId": "case-familiar"})
        for _ in range(100):
            _, run = api.handle_get(f"/api/investigations/{body['runId']}")
            if run["state"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual((run["state"], run["architecture"], run["run_header"]["architecture"]), ("completed", "team", "team"))
        self.assertEqual(run["consultation_count"], 3)
        self.assertEqual(api.handle_post("/api/investigations", {"caseId": "case-familiar",
                                                                  "configuration": {"architecture": "bogus"}})[0], 400)

    def test_team_experiments_report_specialist_sequences(self):
        api.set_manager(RunManager(model_factory=AutoTeam, jev_factory=FakeJev, alert_store=AlertStore(":memory:")))
        _, body = api.handle_post("/api/experiments/repeat", {"caseId": "case-familiar", "repetitions": 3})
        for _ in range(100):
            _, exp = api.handle_get(f"/api/experiments/{body['experimentId']}")
            if exp["state"] == "completed":
                break
            time.sleep(0.05)
        s = exp["summary"]
        self.assertEqual(s["specialist_sequences"], {"behavior_device > recipient_network > risk_judge": 3})
        self.assertEqual(s["architectures"], ["team"])

    def test_team_ablation_arms_differ_only_by_the_risk_judge(self):
        api.set_manager(RunManager(model_factory=AutoTeam, jev_factory=FakeJev, alert_store=AlertStore(":memory:")))
        _, body = api.handle_post("/api/experiments/ablation", {"caseIds": ["case-familiar", "case-takeover"], "repetitions": 2})
        for _ in range(200):
            _, exp = api.handle_get(f"/api/experiments/{body['experimentId']}")
            if exp["state"] == "completed":
                break
            time.sleep(0.05)
        arms = exp["summary"]["arms"]
        for arm in ("no_jev", "with_jev"):
            self.assertEqual((arms[arm]["matched_runs"], arms[arm]["eligible_runs"]), (4, 4))
        no_jev = arms["no_jev"]["cases"]["case-familiar"]["summary"]["specialist_sequences"]
        with_jev = arms["with_jev"]["cases"]["case-familiar"]["summary"]["specialist_sequences"]
        self.assertEqual(no_jev, {"behavior_device > recipient_network": 2})
        self.assertEqual(with_jev, {"behavior_device > recipient_network > risk_judge": 2})


if __name__ == "__main__":
    unittest.main()
