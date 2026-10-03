"""Alert feature tests: Jev triage -> alert creation, with policy guardrails."""

import os
import tempfile
import time
import unittest

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)
os.environ["EVIDENCETRAIL_ALERT_DB"] = ":memory:"

from evidencetrail import agent, alerts, api, evaluator
from evidencetrail.alerts import AlertStore, decide_alert
from evidencetrail.evidence import EvidenceStore
from evidencetrail.runs import RunManager
from evidencetrail.scenarios import get_case
from test_evidencetrail import FakeJev, ScriptedFor, ScriptedModel, finisher, full_plan

SUSPICIOUS = {"suspicion": "SUSPICIOUS", "severity": 2}


def run(case_id, jev, agent_action="ALLOW", triage=True):
    case = get_case(case_id)
    model = ScriptedModel(full_plan(case), finisher(agent_action))
    return case, agent.investigate(case, model, jev, "run-alert", triage=triage)


class AlertDecision(unittest.TestCase):
    def test_jev_and_policy_agree_creates_one_high_alert(self):
        _, r = run("case-takeover", FakeJev(triage=SUSPICIOUS))
        a = r["alert"]
        self.assertEqual((a["sources"], a["severity"], a["disagreement"]), (["jev", "policy"], "high", None))
        self.assertEqual(a["policy"]["action"], "REVIEW")
        self.assertEqual(a["status"], "open")
        self.assertTrue(a["synthetic"])

    def test_jev_alone_can_raise_an_alert_but_not_change_the_action(self):
        _, with_triage = run("case-familiar", FakeJev(triage=SUSPICIOUS))
        _, without = run("case-familiar", FakeJev(triage=SUSPICIOUS), triage=False)
        a = with_triage["alert"]
        self.assertEqual((a["sources"], a["severity"]), (["jev"], "high"))
        self.assertEqual(a["disagreement"], "jev_suspicious_policy_allow")
        self.assertEqual(with_triage["final"]["simulated_action"], "ALLOW")
        self.assertEqual(with_triage["final"]["simulated_action"], without["final"]["simulated_action"])

    def test_jev_not_suspicious_cannot_suppress_a_policy_alert(self):
        _, r = run("case-takeover", FakeJev(triage={"suspicion": "NOT_SUSPICIOUS", "severity": 0}))
        a = r["alert"]
        self.assertEqual((a["sources"], a["severity"]), (["policy"], "high"))
        self.assertEqual(a["disagreement"], "policy_flagged_jev_not_suspicious")
        self.assertIn("alert stands", a["summary"])

    def test_context_check_policy_gives_medium_severity(self):
        _, r = run("case-manipulated", FakeJev(triage={"suspicion": "NOT_SUSPICIOUS", "severity": 0}))
        self.assertEqual(r["alert"]["severity"], "medium")
        self.assertEqual(r["alert"]["title"], "Context check recommended")

    def test_quiet_case_creates_no_alert_and_says_so_in_the_trace(self):
        _, r = run("case-familiar", FakeJev())
        self.assertIsNone(r["alert"])
        self.assertEqual(r["events"][-1]["event_type"], "alert_not_created")

    def test_jev_unavailable_is_visible_and_never_fabricated(self):
        _, quiet = run("case-familiar", FakeJev(fail=True))
        self.assertIsNone(quiet["alert"])  # policy allowed it and Jev could not judge
        triage_ev = [e for e in quiet["evidence"] if e["type"] == "alert_triage"][0]
        self.assertEqual(triage_ev["payload"]["status"], "unavailable")
        _, flagged = run("case-takeover", FakeJev(fail=True))
        self.assertEqual(flagged["alert"]["disagreement"], "jev_unavailable")
        self.assertEqual(flagged["alert"]["sources"], ["policy"])
        self.assertEqual(flagged["alert"]["jev_triage"]["status"], "unavailable")

    def test_unexpected_jev_answer_is_an_error_not_a_guess(self):
        _, r = run("case-familiar", FakeJev(triage={"suspicion": "MAYBE", "severity": 1}))
        ev = [e for e in r["evidence"] if e["type"] == "alert_triage"][0]
        self.assertEqual(ev["payload"]["status"], "error")
        self.assertIsNone(r["alert"])

    def test_incomplete_investigation_alerts_from_policy(self):
        _, r = run("case-missing-tool", FakeJev())
        a = r["alert"]
        self.assertEqual((a["title"], a["severity"], a["sources"]), ("Investigation incomplete: evidence missing", "high", ["policy"]))

    def test_provider_outage_with_no_evidence_skips_jev_and_alerts(self):
        from evidencetrail.gemini import GeminiClient
        saved = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
        try:
            jev = FakeJev()
            r = agent.investigate(get_case("case-familiar"), GeminiClient(), jev, "run-out", triage=True)
        finally:
            for k, v in saved.items():
                if v:
                    os.environ[k] = v
        self.assertEqual(jev.triage_states, [])  # nothing to assess, Jev not called
        self.assertEqual(r["alert"]["severity"], "high")
        self.assertEqual(r["alert"]["jev_triage"]["status"], "skipped")

    def test_decide_alert_truth_table(self):
        allow = {"status": "COMPLETE", "simulated_action": "ALLOW"}
        review = {"status": "COMPLETE", "simulated_action": "REVIEW"}
        ok = lambda s: {"status": "ok", "suspicion": s}
        self.assertEqual(decide_alert(ok("SUSPICIOUS"), allow)[:2], (True, ["jev"]))
        self.assertEqual(decide_alert(ok("NOT_SUSPICIOUS"), allow)[0], False)
        self.assertEqual(decide_alert(ok("UNDETERMINED"), allow)[0], False)
        self.assertEqual(decide_alert(ok("UNDETERMINED"), review)[:2], (True, ["policy"]))
        self.assertEqual(decide_alert(ok("SUSPICIOUS"), review)[:2], (True, ["jev", "policy"]))


class TriageInputAndOrdering(unittest.TestCase):
    def test_jev_never_sees_policy_outcome_or_case_identity(self):
        jev = FakeJev(triage=SUSPICIOUS)
        case, _ = run("case-manipulated", jev)
        state = jev.triage_states[0]
        self.assertIn("TRANSACTION:", state)
        self.assertIn("24500", state)
        for hidden in ("CONTEXT_CHECK", "REVIEW", "ALLOW", case["case_id"], case["name"], "policy"):
            self.assertNotIn(hidden, state)

    def test_triage_runs_after_the_final_decision(self):
        _, r = run("case-takeover", FakeJev(triage=SUSPICIOUS))
        types = [e["event_type"] for e in r["events"]]
        self.assertLess(types.index("final_decision"), types.index("alert_triage"))
        self.assertEqual(types[-1], "alert_created")

    def test_triage_evidence_is_excluded_from_g_eval_context_and_jev_state(self):
        case, r = run("case-familiar", FakeJev())
        run_view = {"events": r["events"], "evidence": r["evidence"]}
        self.assertFalse(any("alert_triage" in line for line in evaluator.evidence_context(run_view)))
        store = EvidenceStore()
        store.add("behavior_profile", "s", None, {"a": 1})
        store.add("alert_triage", "alert_triage", None, {"status": "ok"})
        self.assertNotIn("alert_triage", alerts.triage_state(case, store))

    def test_alert_events_are_in_the_verified_hash_chain(self):
        from evidencetrail.trace import verify_chain
        _, r = run("case-takeover", FakeJev(triage=SUSPICIOUS))
        self.assertTrue(verify_chain(r["events"]))


class AlertStoreTests(unittest.TestCase):
    def _alert(self, severity="high", status="open", n=1):
        _, r = run("case-takeover", FakeJev(triage=SUSPICIOUS))
        a = dict(r["alert"])
        a["alert_id"], a["severity"], a["status"] = f"ALT-T{n}", severity, status
        return a

    def test_create_get_filter_and_status_history(self):
        store = AlertStore(":memory:")
        store.create(self._alert("high", n=1))
        store.create(self._alert("medium", n=2))
        self.assertEqual(len(store.list()), 2)
        self.assertEqual([a["alert_id"] for a in store.list(severity="medium")], ["ALT-T2"])
        updated = store.set_status("ALT-T1", "acknowledged", "looking")
        self.assertEqual(updated["status"], "acknowledged")
        self.assertEqual([h["status"] for h in updated["history"]], ["open", "acknowledged"])
        self.assertEqual(len(store.list(status="open")), 1)
        with self.assertRaises(ValueError):
            store.set_status("ALT-T1", "deleted")
        self.assertIsNone(store.set_status("ALT-NOPE", "dismissed"))

    def test_alerts_persist_in_a_file_across_store_instances(self):
        path = os.path.join(tempfile.mkdtemp(), "alerts.db")
        AlertStore(path).create(self._alert(n=7))
        again = AlertStore(path)
        self.assertEqual(again.get("ALT-T7")["case_id"], "case-takeover")
        again._conn.close()
        AlertStore(path)._db().close()


class AlertApi(unittest.TestCase):
    def setUp(self):
        self.jev = FakeJev(triage=SUSPICIOUS)
        self.mgr = RunManager(architecture="single", model_factory=ScriptedFor, jev_factory=lambda: self.jev,
                              alert_store=AlertStore(":memory:"))
        api.set_manager(self.mgr)

    def _finish(self, run_id):
        for _ in range(100):
            _, r = api.handle_get(f"/api/investigations/{run_id}")
            if r["state"] in ("completed", "failed"):
                return r
            time.sleep(0.05)
        self.fail("run did not finish")

    def test_investigation_creates_a_persisted_alert_and_queue_lists_it(self):
        _, body = api.handle_post("/api/investigations", {"caseId": "case-takeover"})
        run_view = self._finish(body["runId"])
        alert = run_view["alert"]
        self.assertEqual(alert["run_id"], body["runId"])
        status, listing = api.handle_get("/api/evidencetrail/alerts")
        self.assertEqual((status, listing["total"]), (200, 1))
        self.assertEqual(api.handle_get(f"/api/evidencetrail/alerts/{alert['alert_id']}")[1]["severity"], "high")
        self.assertEqual(api.handle_get("/api/evidencetrail/alerts", {"severity": ["low"]})[1]["total"], 0)

    def test_status_transitions_and_validation(self):
        _, body = api.handle_post("/api/investigations", {"caseId": "case-takeover"})
        aid = self._finish(body["runId"])["alert"]["alert_id"]
        status, a = api.handle_post(f"/api/evidencetrail/alerts/{aid}/status", {"status": "acknowledged", "note": "on it"})
        self.assertEqual((status, a["status"]), (200, "acknowledged"))
        self.assertEqual(api.handle_get("/api/evidencetrail/alerts", {"status": ["open"]})[1]["total"], 0)
        self.assertEqual(api.handle_post(f"/api/evidencetrail/alerts/{aid}/status", {"status": "deleted"})[0], 400)
        self.assertEqual(api.handle_post(f"/api/evidencetrail/alerts/{aid}/status", {"status": "dismissed", "note": 5})[0], 400)
        self.assertEqual(api.handle_post("/api/evidencetrail/alerts/ALT-NOPE/status", {"status": "dismissed"})[0], 404)
        self.assertEqual(api.handle_get("/api/evidencetrail/alerts/ALT-NOPE")[0], 404)

    def test_list_filters_accept_all_and_reject_unknown_values(self):
        _, body = api.handle_post("/api/investigations", {"caseId": "case-takeover"})
        aid = self._finish(body["runId"])["alert"]["alert_id"]
        api.handle_post(f"/api/evidencetrail/alerts/{aid}/status", {"status": "dismissed"})
        self.assertEqual(api.handle_get("/api/evidencetrail/alerts", {"status": ["all"]})[1]["total"], 1)
        self.assertEqual(api.handle_get("/api/evidencetrail/alerts", {"status": ["open"]})[1]["total"], 0)
        self.assertEqual(api.handle_get("/api/evidencetrail/alerts", {"status": ["bogus"]})[0], 400)
        self.assertEqual(api.handle_get("/api/evidencetrail/alerts", {"severity": ["urgent"]})[0], 400)

    def test_experiments_never_create_alerts_or_call_triage(self):
        _, body = api.handle_post("/api/experiments/repeat", {"caseId": "case-takeover", "repetitions": 3})
        for _ in range(100):
            _, exp = api.handle_get(f"/api/experiments/{body['experimentId']}")
            if exp["state"] == "completed":
                break
            time.sleep(0.05)
        _, ab = api.handle_post("/api/experiments/ablation", {"caseIds": ["case-takeover"], "repetitions": 1})
        time.sleep(1.0)
        self.assertEqual(self.jev.triage_states, [])
        self.assertEqual(api.handle_get("/api/evidencetrail/alerts")[1]["total"], 0)

    def test_export_includes_the_alert(self):
        _, body = api.handle_post("/api/investigations", {"caseId": "case-takeover"})
        self._finish(body["runId"])
        export = api.handle_get(f"/api/investigations/{body['runId']}/export")[1]
        self.assertEqual(export["alert"]["case_id"], "case-takeover")

    def test_alert_save_failure_is_reported_not_swallowed(self):
        class BrokenStore(AlertStore):
            def create(self, alert):
                import sqlite3
                raise sqlite3.OperationalError("disk full")
        mgr = RunManager(architecture="single", model_factory=ScriptedFor, jev_factory=lambda: self.jev, alert_store=BrokenStore(":memory:"))
        api.set_manager(mgr)
        _, body = api.handle_post("/api/investigations", {"caseId": "case-takeover"})
        view = self._finish(body["runId"])
        self.assertIn("could not be saved", view["alert_error"])
        self.assertEqual(view["alert"]["severity"], "high")  # still shown to the user


if __name__ == "__main__":
    unittest.main()
