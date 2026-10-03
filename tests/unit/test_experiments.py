"""Fixed-evidence experiment, ablation, export, provenance, streaming and judge-repeat tests."""

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)

import json
import time
import unittest

from evidencetrail import agent, api, evaluator
from evidencetrail.eval_fixtures import EXPECTED_ACTIONS
from evidencetrail.experiments import fixed_evidence_experiment, gather_all, rules_baseline
from evidencetrail.gemini import ModelTurn
from evidencetrail.jev import ProviderUnavailable
from evidencetrail.runs import RunManager
from evidencetrail.scenarios import SCENARIOS, get_case
from evidencetrail.evidence import EvidenceStore
from evidencetrail.tools import FINISH
from test_evidencetrail import FakeJev, ScriptedFor, ScriptedModel, finisher, full_plan
from test_geval import HAVE_DEEPEVAL


class FrozenDecider:
    """Decision model for experiment B: cites every evidence ID in the frozen bundle."""
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
        call = {"id": f"f{i}", "name": FINISH, "arguments": args}
        return ModelTurn([{"type": "function_call", **call}], [call], "", "frozen-1", None)


class VaryingJev(FakeJev):
    def assess(self, state, questions=None):
        self.states.append(state)
        risk = "HIGH" if len(self.states) % 2 else "ELEVATED"
        return {"raw": {"answers": {}}, "normalized": {"recipient_risk": risk, "manipulation_indicators": 0.5},
                "model": "jev-fake-1", "usage": None}


class FixedEvidence(unittest.TestCase):
    def test_decision_and_jev_compared_separately_with_raw_counts(self):
        case = get_case("case-manipulated")
        out = fixed_evidence_experiment(case, FrozenDecider(["CONTEXT_CHECK"]), VaryingJev(), 4)
        self.assertEqual(out["decision"]["attempted"], 4)
        self.assertEqual(out["decision"]["successful"], 4)
        self.assertEqual(out["decision"]["action_counts"]["CONTEXT_CHECK"], 4)
        risk = out["jev"]["per_question"]["recipient_risk"]
        self.assertEqual(risk["counts"], {"HIGH": 2, "ELEVATED": 2})
        self.assertEqual(out["jev"]["per_question"]["manipulation_indicators"]["mean"], 0.5)

    def test_bundle_is_frozen_and_label_free(self):
        case = get_case("case-manipulated")
        model = FrozenDecider()
        out = fixed_evidence_experiment(case, model, FakeJev(), 3)
        prompts = [steps[0]["content"] for steps, _ in model.seen]
        self.assertEqual(len(set(prompts)), 1)  # identical frozen input every time
        self.assertEqual(len(out["bundle"]["bundle_hash"]), 64)
        self.assertNotIn(case["name"], prompts[0])
        self.assertNotIn(case["case_id"], prompts[0])
        self.assertTrue(all([t["name"] for t in tools] == [FINISH] for _, tools in model.seen))

    def test_failures_are_counted_not_hidden(self):
        case = get_case("case-familiar")
        out = fixed_evidence_experiment(case, FrozenDecider(["ALLOW"], fail_at={1}), FakeJev(fail=True), 3)
        self.assertEqual((out["decision"]["attempted"], out["decision"]["successful"]), (3, 2))
        self.assertEqual(out["decision"]["incomplete_or_error"], 1)
        self.assertEqual((out["jev"]["successful"], out["jev"]["errors"]), (0, 3))

    def test_policy_still_controls_the_action(self):
        out = fixed_evidence_experiment(get_case("case-takeover"), FrozenDecider(["ALLOW"]), FakeJev(), 2)
        self.assertEqual(out["decision"]["action_counts"]["REVIEW"], 2)  # agent said ALLOW; policy wins

    def test_api_mode_runs_in_background(self):
        api.set_manager(RunManager(model_factory=FrozenDecider, jev_factory=FakeJev))
        status, body = api.handle_post("/api/experiments/repeat",
                                       {"caseId": "case-familiar", "mode": "fixed_evidence", "repetitions": 3})
        self.assertEqual(status, 202)
        for _ in range(100):
            _, exp = api.handle_get(f"/api/experiments/{body['experimentId']}")
            if exp["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(exp["state"], "completed")
        self.assertEqual(exp["result"]["decision"]["attempted"], 3)
        self.assertEqual(api.handle_post("/api/experiments/repeat",
                                         {"caseId": "case-familiar", "mode": "bogus"})[0], 400)


class Ablation(unittest.TestCase):
    def test_rules_arm_reproduces_every_policy_label_without_any_model(self):
        for cid in SCENARIOS:
            r = rules_baseline(get_case(cid))
            self.assertEqual(r["final"]["simulated_action"], EXPECTED_ACTIONS[cid], cid)
            self.assertIsNone(r["final"]["agent_recommendation"])

    def test_gather_all_marks_failed_tool_as_error_evidence(self):
        store = gather_all(get_case("case-missing-tool"))
        self.assertEqual([e["source"] for e in store.by_type("tool_error")], ["inspect_recipient"])

    def test_no_jev_arm_unregisters_only_the_jev_tool(self):
        names_with = [d["name"] for d in agent.registered_tools(True)]
        names_without = [d["name"] for d in agent.registered_tools(False)]
        self.assertEqual(set(names_with) - set(names_without), {"assess_with_jev"})

    def test_no_jev_arm_rejects_a_jev_call_and_records_the_arm(self):
        case = get_case("case-familiar")
        plan = full_plan(case) + [("assess_with_jev", {"evidence_ids": ["EV-001"]})]
        model = ScriptedModel(plan, finisher())
        jev = FakeJev()
        r = agent.investigate(case, model, jev, "run-nojev", enable_jev=False)
        self.assertEqual(jev.states, [])
        errs = [e for e in r["evidence"] if e["type"] == "tool_error"]
        self.assertIn("not registered", errs[0]["payload"]["error"])
        self.assertEqual(r["run_header"]["arm"], "no_jev")
        self.assertNotEqual(r["run_header"]["tool_snapshot_hash"],
                            agent.run_header(case, "live", model)["tool_snapshot_hash"])

    def test_ablation_api_reports_all_arms_with_denominators(self):
        api.set_manager(RunManager(architecture="single", model_factory=ScriptedFor, jev_factory=FakeJev))
        status, body = api.handle_post("/api/experiments/ablation",
                                       {"caseIds": ["case-familiar", "case-takeover"], "repetitions": 2})
        self.assertEqual(status, 202)
        for _ in range(200):
            _, exp = api.handle_get(f"/api/experiments/{body['experimentId']}")
            if exp["state"] == "completed":
                break
            time.sleep(0.05)
        arms = exp["summary"]["arms"]
        self.assertEqual((arms["rules"]["matched"], arms["rules"]["eligible"]), (2, 2))
        for arm in ("no_jev", "with_jev"):
            self.assertEqual(arms[arm]["attempted_runs"], 4)
            self.assertEqual((arms[arm]["matched_runs"], arms[arm]["eligible_runs"]), (4, 4))

    def test_incomplete_outcome_counts_for_missing_tool_case_but_provider_outage_does_not(self):
        api.set_manager(RunManager(architecture="single", model_factory=ScriptedFor, jev_factory=FakeJev))
        _, body = api.handle_post("/api/experiments/ablation", {"caseIds": ["case-missing-tool"], "repetitions": 2})
        for _ in range(200):
            _, exp = api.handle_get(f"/api/experiments/{body['experimentId']}")
            if exp["state"] == "completed":
                break
            time.sleep(0.05)
        arm = exp["summary"]["arms"]["with_jev"]
        self.assertEqual((arm["matched_runs"], arm["eligible_runs"]), (2, 2))  # INCOMPLETE/REVIEW is expected
        import os
        saved = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
        try:
            from evidencetrail.gemini import GeminiClient
            api.set_manager(RunManager(model_factory=GeminiClient, jev_factory=FakeJev))
            _, body = api.handle_post("/api/experiments/ablation", {"caseIds": ["case-takeover"], "repetitions": 2})
            for _ in range(200):
                _, exp = api.handle_get(f"/api/experiments/{body['experimentId']}")
                if exp["state"] == "completed":
                    break
                time.sleep(0.05)
        finally:
            for k, v in saved.items():
                if v:
                    os.environ[k] = v
        out = exp["summary"]["arms"]["with_jev"]
        self.assertEqual((out["matched_runs"], out["eligible_runs"], out["attempted_runs"]), (0, 0, 2))
        self.assertEqual(api.handle_post("/api/experiments/ablation", {"caseIds": []})[0], 400)
        self.assertEqual(api.handle_post("/api/experiments/ablation", {"caseIds": ["nope"]})[0], 404)


class TraceExportAndProvenance(unittest.TestCase):
    def _run(self):
        case = get_case("case-familiar")
        return agent.investigate(case, ScriptedModel(full_plan(case), finisher()), FakeJev(), "run-x")

    def test_run_header_records_code_commit_state(self):
        header = self._run()["run_header"]
        self.assertIn("commit", header["code"])
        self.assertIn("dirty", header["code"])
        for key in ("tool_snapshot_hash", "scenario_version", "model_configuration", "run_mode"):
            self.assertIn(key, header)

    def test_model_turns_keep_exact_redacted_request_and_response(self):
        events = [e for e in self._run()["events"] if e["event_type"] == "model_turn"]
        snap = events[1]["result_snapshot"]
        self.assertEqual(len(snap["request_hash"]), 64)
        self.assertTrue(snap["request_steps"])
        self.assertTrue(snap["response_steps"])
        self.assertGreater(len(snap["request_steps"]), len(events[0]["result_snapshot"]["request_steps"]))

    def test_export_is_redacted_and_labelled_not_immutable(self):
        mgr = RunManager(architecture="single", model_factory=ScriptedFor, jev_factory=FakeJev)
        api.set_manager(mgr)
        _, body = api.handle_post("/api/investigations", {"caseId": "case-familiar"})
        for _ in range(100):
            if mgr.get(body["runId"])["state"] == "completed":
                break
            time.sleep(0.05)
        mgr._runs[body["runId"]]["evidence"].append(
            {"evidence_id": "EV-X", "payload": {"Authorization": "Bearer sk-test-123"}})
        status, export = api.handle_get(f"/api/investigations/{body['runId']}/export")
        self.assertEqual(status, 200)
        self.assertNotIn("sk-test-123", json.dumps(export))
        self.assertIn("not immutable", export["export_notice"])
        self.assertTrue(export["hash_chain_verified"])
        self.assertEqual(api.handle_get("/api/investigations/run-nope/export")[0], 404)

    def test_evidence_streams_while_run_is_in_progress(self):
        case = get_case("case-familiar")
        store, seen = EvidenceStore(), []
        agent.investigate(case, ScriptedModel(full_plan(case), finisher()), FakeJev(), "run-s",
                          on_event=lambda e: seen.append(len(store.all())), store=store)
        self.assertEqual(seen[0], 0)
        self.assertTrue(any(0 < n < 4 for n in seen))  # partial evidence visible mid-run
        self.assertEqual(seen[-1], 4)


@unittest.skipUnless(HAVE_DEEPEVAL, "deepeval not installed")
class JudgeRepeats(unittest.TestCase):
    def test_repeated_judge_passes_report_each_score_and_spread(self):
        from test_geval import StubJudge
        case = get_case("case-manipulated")
        run = agent.investigate(case, ScriptedModel(full_plan(case), finisher("CONTEXT_CHECK")), FakeJev(), "run-j")
        judge = StubJudge()
        out = evaluator.evaluate(run, case, judge_factory=lambda: judge, repeats=3)
        m = out["geval"]["evidence_grounding"]
        self.assertEqual((m["passes_attempted"], m["passes_successful"]), (3, 3))
        self.assertEqual(len(m["scores"]), 3)
        self.assertLessEqual(m["score_min"], m["score_max"])
        self.assertEqual(out["judge_passes_requested"], 3)

    def test_api_validates_repeats(self):
        api.set_manager(RunManager(architecture="single", model_factory=ScriptedFor, jev_factory=FakeJev))
        _, body = api.handle_post("/api/investigations", {"caseId": "case-familiar"})
        status, _ = api.handle_post(f"/api/investigations/{body['runId']}/evaluate", {"repeats": 9})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
