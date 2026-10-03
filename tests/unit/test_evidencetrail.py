"""EvidenceTrail tests. Scripted fake model and fake Jev: no network, no credentials."""

import os
import time
import unittest

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)
os.environ["EVIDENCETRAIL_ALERT_DB"] = ":memory:"  # never touch the real alert database in tests

from evidencetrail import agent, api, policy
from evidencetrail.canon import redact
from evidencetrail.evidence import EvidenceStore
from evidencetrail.jev import JevClient, ProviderUnavailable
from evidencetrail.metrics import modal_agreement, pairwise_agreement
from evidencetrail.runs import RunManager
from evidencetrail.scenarios import apply_counterfactual, get_case, list_scenarios
from evidencetrail.gemini import ModelTurn
from evidencetrail.tools import FINISH
from evidencetrail.trace import verify_chain


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


class ScriptedModel:
    """Plays a fixed list of tool calls, then finishes with caller-provided claims."""
    provider = "scripted"
    requested_model = "scripted-model"

    def __init__(self, plan, finish_builder):
        self.plan = list(plan)
        self.finish_builder = finish_builder
        self.seen_inputs = []

    def generate(self, system, steps, tools):
        self.seen_inputs.append(steps)
        results = [s for s in steps if s.get("type") == "function_result"]
        if self.plan:
            name, args = self.plan.pop(0)
            call = {"id": f"c{len(results)}", "name": name, "arguments": args}
        else:
            call = {"id": "cfin", "name": FINISH, "arguments": self.finish_builder(results)}
        return ModelTurn([{"type": "function_call", **call}], [call], "", "scripted-1", None)


def _ids(results):
    import json
    return [json.loads(r["result"][0]["text"]).get("evidence_id") for r in results]


def full_plan(case):
    tx = case["transaction"]
    return [("get_behavior_profile", {"customer_id": tx["customer_id"]}),
            ("inspect_device", {"transaction_id": tx["transaction_id"]}),
            ("inspect_recipient", {"recipient_id": tx["recipient_id"]}),
            ("search_relationship_graph", {"recipient_id": tx["recipient_id"], "max_hops": 2})]


def finisher(action="ALLOW", status="COMPLETE"):
    def build(results):
        ids = [i for i in _ids(results) if i]
        return {"recommended_action": action, "status": status,
                "claims": [{"text": "Checks reviewed.", "supporting_evidence_ids": ids[:2]}],
                "remaining_uncertainty": "none material"}
    return build


def run_case(case_id, action="ALLOW", jev=None, plan=None):
    case = get_case(case_id)
    model = ScriptedModel(plan if plan is not None else full_plan(case), finisher(action))
    return case, model, agent.investigate(case, model, jev or FakeJev(), "run-test")


class PolicyOutcomes(unittest.TestCase):
    def test_familiar_allow(self):
        _, _, r = run_case("case-familiar")
        self.assertEqual((r["final"]["status"], r["final"]["simulated_action"]), ("COMPLETE", "ALLOW"))

    def test_takeover_review(self):
        _, _, r = run_case("case-takeover", action="ALLOW")  # agent says ALLOW; policy overrides
        self.assertEqual(r["final"]["simulated_action"], "REVIEW")
        self.assertEqual(r["final"]["rule"], "device_compromise")

    def test_manipulated_context_check_then_coercion_review(self):
        _, _, r = run_case("case-manipulated")
        final = r["final"]
        self.assertEqual(final["simulated_action"], "CONTEXT_CHECK")
        self.assertIn("safe account", final["context_check"]["question"])
        policy.apply_context_answer(final, "yes")
        self.assertEqual(final["simulated_action"], "REVIEW")

    def test_policy_label_compares_pre_answer_action(self):
        from evidencetrail.metrics import deterministic_checks
        _, _, r = run_case("case-manipulated")
        run = {"case_id": "case-manipulated", "final": r["final"], "events": r["events"],
               "tool_call_count": r["tool_call_count"]}
        policy.apply_context_answer(run["final"], "yes")
        self.assertEqual(run["final"]["simulated_action"], "REVIEW")
        self.assertTrue(deterministic_checks(run)["policy_label_match"])

    def test_context_check_no_does_not_clear_signals(self):
        _, _, r = run_case("case-manipulated")
        final = policy.apply_context_answer(r["final"], "no")
        self.assertEqual(final["simulated_action"], "CONTEXT_CHECK")
        self.assertTrue(final["signals"])

    def test_legit_high_value_allow(self):
        _, _, r = run_case("case-legit-high")
        self.assertEqual(r["final"]["simulated_action"], "ALLOW")

    def test_missing_tool_response_is_incomplete_review(self):
        _, _, r = run_case("case-missing-tool")
        self.assertEqual((r["final"]["status"], r["final"]["simulated_action"]), ("INCOMPLETE", "REVIEW"))
        self.assertTrue(any(e["type"] == "tool_error" for e in r["evidence"]))

    def test_skipped_checks_are_not_reassuring(self):
        _, _, r = run_case("case-familiar", plan=[])
        self.assertEqual(r["final"]["status"], "INCOMPLETE")

    def test_policy_controls_the_action_and_a_more_cautious_agent_is_flagged_not_obeyed(self):
        _, _, r = run_case("case-familiar", action="REVIEW")
        f = r["final"]
        self.assertEqual(f["simulated_action"], "ALLOW")
        self.assertFalse(f["agent_escalation"])
        self.assertEqual(f["agent_disagreement"], "agent_more_cautious")
        self.assertIn("policy v1 outcome (ALLOW) takes precedence", f["explanation"])

    def test_escalation_is_an_explicit_opt_in(self):
        os.environ["EVIDENCETRAIL_AGENT_ESCALATION"] = "1"
        try:
            _, _, r = run_case("case-familiar", action="REVIEW")
        finally:
            del os.environ["EVIDENCETRAIL_AGENT_ESCALATION"]
        self.assertEqual(r["final"]["simulated_action"], "REVIEW")
        self.assertTrue(r["final"]["agent_escalation"])
        self.assertIsNone(r["final"]["agent_disagreement"])

    def test_a_less_cautious_agent_never_lowers_the_policy_and_is_flagged(self):
        _, _, r = run_case("case-takeover", action="ALLOW")
        self.assertEqual(r["final"]["simulated_action"], "REVIEW")
        self.assertEqual(r["final"]["agent_disagreement"], "agent_less_cautious")

    def test_invented_evidence_id_is_incomplete(self):
        case = get_case("case-familiar")
        model = ScriptedModel(full_plan(case), lambda _r: {
            "recommended_action": "ALLOW", "status": "COMPLETE", "remaining_uncertainty": "",
            "claims": [{"text": "Made up", "supporting_evidence_ids": ["EV-999"]}]})
        r = agent.investigate(case, model, FakeJev(), "run-test")
        self.assertEqual(r["final"]["status"], "INCOMPLETE")
        self.assertEqual(r["final"]["reference_validity"], {"cited": 1, "valid": 0})


class AgentBoundaries(unittest.TestCase):
    def test_agent_never_sees_case_id_name_or_label(self):
        case, model, _ = run_case("case-manipulated")
        blob = str(model.seen_inputs) + agent.SYSTEM_PROMPT
        for secret in (case["case_id"], case["name"], "CONTEXT_CHECK expected"):
            self.assertNotIn(secret, blob)
        self.assertNotIn("EXPECTED", blob)

    def test_bad_arguments_become_visible_tool_errors(self):
        tx = get_case("case-familiar")["transaction"]
        plan = [("inspect_recipient", {"recipient_id": "RCP-OTHER"}),
                ("search_relationship_graph", {"recipient_id": tx["recipient_id"], "max_hops": 5})]
        _, _, r = run_case("case-familiar", plan=plan)
        errors = [e for e in r["events"] if e["event_type"] == "tool_error"]
        self.assertEqual(len(errors), 2)
        self.assertEqual(r["final"]["status"], "INCOMPLETE")

    def test_tool_budget_is_enforced(self):
        tx = get_case("case-familiar")["transaction"]
        plan = [("inspect_device", {"transaction_id": tx["transaction_id"]})] * 12
        _, _, r = run_case("case-familiar", plan=plan)
        self.assertEqual(r["tool_call_count"], 8)

    def test_graph_respects_hop_limit(self):
        case = get_case("case-manipulated")
        tx = case["transaction"]
        one = [("search_relationship_graph", {"recipient_id": tx["recipient_id"], "max_hops": 1})]
        _, _, r = run_case("case-manipulated", plan=one)
        graph = [e for e in r["evidence"] if e["type"] == "relationship_graph"][0]["payload"]
        self.assertEqual(graph["synthetically_flagged_node_ids"], [])
        self.assertEqual(len(graph["links"]), 1)

    def test_jev_participates_and_is_retained(self):
        case = get_case("case-manipulated")
        plan = full_plan(case) + [("assess_with_jev", {"evidence_ids": ["EV-001", "EV-003"]})]
        jev = FakeJev()
        _, _, r = run_case("case-manipulated", jev=jev, plan=plan)
        ev = [e for e in r["evidence"] if e["type"] == "jev_assessment"][0]
        self.assertEqual(ev["payload"]["normalized"]["recipient_risk"], "HIGH")
        self.assertIn("raw", ev["payload"])
        self.assertEqual(ev["payload"]["model"], "jev-fake-1")
        self.assertNotIn("case-manipulated", jev.states[0])

    def test_jev_outage_is_visible_missing_evidence(self):
        plan = [("assess_with_jev", {"evidence_ids": ["EV-001"]})]
        case = get_case("case-familiar")
        model = ScriptedModel(full_plan(case)[:1] + plan, finisher())
        r = agent.investigate(case, model, FakeJev(fail=True), "run-test")
        errs = [e for e in r["evidence"] if e["type"] == "tool_error"]
        self.assertTrue(errs and errs[0]["payload"]["unavailable"])

    def test_missing_credentials_never_fabricate_success(self):
        import os
        from evidencetrail.gemini import GeminiClient
        saved = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
        try:
            r = agent.investigate(get_case("case-familiar"), GeminiClient(), JevClient(), "run-test")
        finally:
            for k, v in saved.items():
                if v:
                    os.environ[k] = v
        self.assertEqual((r["final"]["status"], r["final"]["simulated_action"]), ("INCOMPLETE", "REVIEW"))
        self.assertIn("not configured", r["failure"])


class TraceAndEvidence(unittest.TestCase):
    def test_hash_chain_verifies_and_detects_tampering(self):
        _, _, r = run_case("case-familiar")
        self.assertTrue(verify_chain(r["events"]))
        r["events"][1]["reason_code"] = "TAMPERED"
        self.assertFalse(verify_chain(r["events"]))

    def test_trace_has_required_fields(self):
        _, _, r = run_case("case-familiar")
        for key in ("trace_id", "run_id", "case_id", "sequence", "timestamp_utc", "event_type", "actor",
                    "tool_name", "validated_arguments", "input_evidence_ids", "output_evidence_ids",
                    "result_snapshot", "reason_code", "prompt_version", "policy_version", "duration_ms",
                    "previous_event_hash", "event_hash"):
            self.assertIn(key, r["events"][0])

    def test_evidence_ids_are_stable_and_hashed(self):
        s = EvidenceStore()
        a = s.add("t", "src", "rec", {"x": 1})
        self.assertEqual(a["evidence_id"], "EV-001")
        self.assertEqual(len(a["snapshot_hash"]), 64)

    def test_redaction_masks_credentials(self):
        out = redact({"headers": {"Authorization": "Bearer abc", "x-goog-api-key": "k"}, "ok": 1})
        self.assertEqual(out["headers"]["Authorization"], "[REDACTED]")
        self.assertEqual(out["headers"]["x-goog-api-key"], "[REDACTED]")
        self.assertEqual(out["ok"], 1)


class ScenariosAndMetrics(unittest.TestCase):
    def test_scenario_list_has_names_and_transaction_only(self):
        for s in list_scenarios():
            self.assertEqual(set(s), {"case_id", "name", "synthetic", "scenario_version", "transaction"})

    def test_counterfactual_preserves_original_and_is_consistent(self):
        original = get_case("case-manipulated")
        clone = apply_counterfactual(original, {"remove_network_links": True})
        rid = original["transaction"]["recipient_id"]
        self.assertTrue(original["world"]["graph"][rid]["links"])
        self.assertEqual(clone["world"]["graph"][rid]["links"], [])
        self.assertEqual(clone["counterfactual_of"], "case-manipulated")

    def test_modal_and_pairwise_agreement(self):
        acts = ["REVIEW", "REVIEW", "ALLOW", "REVIEW"]
        self.assertEqual(modal_agreement(acts)["agreement"], "3/4")
        self.assertAlmostEqual(pairwise_agreement(acts), (3 * 2 + 0) / (4 * 3))
        self.assertIsNone(pairwise_agreement(["ALLOW"]))


class ApiFlow(unittest.TestCase):
    def setUp(self):
        def factory():
            case_model = {}
            return ScriptedFor()
        api.set_manager(RunManager(architecture="single", model_factory=ScriptedFor, jev_factory=FakeJev))

    def _wait(self, run_id):
        for _ in range(100):
            _, run = api.handle_get(f"/api/investigations/{run_id}")
            if run["state"] in ("completed", "failed"):
                return run
            time.sleep(0.05)
        self.fail("run did not finish")

    def test_start_poll_evaluate(self):
        status, body = api.handle_post("/api/investigations", {"caseId": "case-familiar"})
        self.assertEqual(status, 202)
        run = self._wait(body["runId"])
        self.assertEqual(run["state"], "completed")
        self.assertTrue(run["recorded_audit_trail_verified"])
        status, ev = api.handle_post(f"/api/investigations/{body['runId']}/evaluate", {})
        self.assertEqual(status, 202)
        for _ in range(100):
            _, run = api.handle_get(f"/api/investigations/{body['runId']}")
            if run["evaluation"] and run["evaluation"]["state"] != "running":
                break
            time.sleep(0.05)
        evaluation = run["evaluation"]
        self.assertTrue(evaluation["deterministic"]["policy_label_match"])
        for metric in evaluation["geval"].values():
            self.assertIn(metric["status"], ("unavailable", "scored", "error"))
            if metric["status"] != "scored":
                self.assertIsNone(metric["score"])

    def test_unknown_case_and_bad_input(self):
        self.assertEqual(api.handle_post("/api/investigations", {"caseId": "nope"})[0], 404)
        self.assertEqual(api.handle_post("/api/experiments/repeat",
                                         {"caseId": "case-familiar", "repetitions": 0})[0], 400)
        self.assertEqual(api.handle_get("/api/investigations/run-missing")[0], 404)

    def test_repeat_experiment_reports_attempts_and_counts(self):
        status, body = api.handle_post("/api/experiments/repeat",
                                       {"caseId": "case-familiar", "repetitions": 3})
        self.assertEqual(status, 202)
        for _ in range(100):
            _, exp = api.handle_get(f"/api/experiments/{body['experimentId']}")
            if exp["state"] == "completed":
                break
            time.sleep(0.05)
        s = exp["summary"]
        self.assertEqual((s["attempted_runs"], s["successful_runs"]), (3, 3))
        self.assertEqual(s["action_counts"]["ALLOW"], 3)


class ScriptedFor(ScriptedModel):
    """Model that investigates whichever transaction appears in the opening message."""

    def __init__(self):
        super().__init__([], finisher())
        self._planned = False

    def generate(self, system, steps, tools):
        import json
        if not self._planned:
            tx = json.loads(steps[0]["content"])["transaction"]
            self.plan = [("get_behavior_profile", {"customer_id": tx["customer_id"]}),
                         ("inspect_device", {"transaction_id": tx["transaction_id"]}),
                         ("inspect_recipient", {"recipient_id": tx["recipient_id"]}),
                         ("search_relationship_graph", {"recipient_id": tx["recipient_id"], "max_hops": 2})]
            self._planned = True
        return super().generate(system, steps, tools)


if __name__ == "__main__":
    unittest.main()
