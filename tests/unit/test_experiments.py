"""Fixed-evidence experiment, ablation, export, provenance, streaming and judge-repeat tests."""

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)

import json
import time
import unittest

from evidencetrail import api, evaluator, team
from evidencetrail.eval_fixtures import EXPECTED_ACTIONS
from evidencetrail.experiments import fixed_evidence_experiment, gather_all, rules_baseline
from evidencetrail.runs import RunManager
from evidencetrail.scenarios import SCENARIOS, get_case
from evidencetrail.evidence import EvidenceStore
from evidencetrail.tools import FINISH
from fakes import AutoTeam, FakeJev, FrozenDecider, VaryingJev, run_team
from test_geval import HAVE_DEEPEVAL


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

    def test_ablation_api_reports_all_arms_with_denominators(self):
        api.set_manager(RunManager(model_factory=AutoTeam, jev_factory=FakeJev))
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
        api.set_manager(RunManager(model_factory=AutoTeam, jev_factory=FakeJev))
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


class FailureReasons(unittest.TestCase):
    def test_failed_runs_explain_themselves_in_summaries(self):
        from evidencetrail.metrics import summarize_runs
        ok = {"state": "completed", "run_id": "r1", "events": [], "final": {"status": "COMPLETE", "simulated_action": "ALLOW", "explanation": "fine"}}
        bad = {"state": "failed", "run_id": "r2", "events": [], "failure": "Model provider unavailable: Gemini HTTP 429: quota",
               "final": {"status": "INCOMPLETE", "simulated_action": "REVIEW", "explanation": "x"}}
        crashed = {"state": "failed", "run_id": "r3", "events": [], "error": "KeyError: boom", "final": None}
        s = summarize_runs([ok, bad, crashed])
        self.assertEqual(s["failures"], [
            {"run_id": "r2", "state": "failed", "reason": "Model provider unavailable: Gemini HTTP 429: quota"},
            {"run_id": "r3", "state": "failed", "reason": "KeyError: boom"}])
        self.assertEqual(s["successful_runs"], 1)


class TraceExportAndProvenance(unittest.TestCase):
    def _run(self):
        return run_team("case-familiar")[2]

    def test_run_header_records_code_commit_state(self):
        header = self._run()["run_header"]
        self.assertIn("commit", header["code"])
        self.assertIn("dirty", header["code"])
        for key in ("tool_snapshot_hash", "scenario_version", "model_configuration", "run_mode"):
            self.assertIn(key, header)

    def test_model_turns_keep_exact_redacted_request_and_response(self):
        events = [e for e in self._run()["events"] if e["event_type"] == "model_turn" and e["agent"] == "orchestrator"]
        snap = events[1]["result_snapshot"]  # the orchestrator's second turn has seen the first consultation
        self.assertEqual(len(snap["request_hash"]), 64)
        self.assertTrue(snap["request_steps"])
        self.assertTrue(snap["response_steps"])
        self.assertGreater(len(snap["request_steps"]), len(events[0]["result_snapshot"]["request_steps"]))

    def test_export_is_redacted_and_labelled_not_immutable(self):
        mgr = RunManager(model_factory=AutoTeam, jev_factory=FakeJev)
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
        team.investigate_team(case, AutoTeam(), FakeJev(), "run-s",
                              on_event=lambda e: seen.append(len(store.all())), store=store)
        self.assertEqual(seen[0], 0)
        self.assertTrue(any(0 < n < 5 for n in seen))  # partial evidence visible mid-run
        self.assertEqual(seen[-1], 5)  # four data tools plus the risk judge's Jev assessment


@unittest.skipUnless(HAVE_DEEPEVAL, "deepeval not installed")
class JudgeRepeats(unittest.TestCase):
    def test_repeated_judge_passes_report_each_score_and_spread(self):
        from test_geval import StubJudge
        case = get_case("case-manipulated")
        run = run_team("case-manipulated", action="CONTEXT_CHECK")[2]
        judge = StubJudge()
        out = evaluator.evaluate(run, case, judge_factory=lambda: judge, repeats=3)
        m = out["geval"]["evidence_grounding"]
        self.assertEqual((m["passes_attempted"], m["passes_successful"]), (3, 3))
        self.assertEqual(len(m["scores"]), 3)
        self.assertLessEqual(m["score_min"], m["score_max"])
        self.assertEqual(out["judge_passes_requested"], 3)

    def test_api_validates_repeats(self):
        api.set_manager(RunManager(model_factory=AutoTeam, jev_factory=FakeJev))
        _, body = api.handle_post("/api/investigations", {"caseId": "case-familiar"})
        status, _ = api.handle_post(f"/api/investigations/{body['runId']}/evaluate", {"repeats": 9})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
