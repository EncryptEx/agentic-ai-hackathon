"""Saved investigation records: written automatically, survive a restart, redacted, and read-only afterwards."""

import json
import os
import tempfile
import time
import unittest

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)

from evidencetrail import api, records
from evidencetrail.alerts import AlertStore
from evidencetrail.runs import RunManager
from fakes import FakeJev, TeamAndDecider


def manager(alert_store=None):
    return RunManager(model_factory=TeamAndDecider, jev_factory=lambda: FakeJev(triage={"suspicion": "SUSPICIOUS", "severity": 2}),
                      alert_store=alert_store or AlertStore(":memory:"))


class RecordDirMixin:
    def setUp(self):
        self._saved = os.environ.get("EVIDENCETRAIL_RECORD_DIR")
        self.dir = tempfile.mkdtemp()
        os.environ["EVIDENCETRAIL_RECORD_DIR"] = self.dir

    def tearDown(self):
        os.environ["EVIDENCETRAIL_RECORD_DIR"] = self._saved

    def finish(self, mgr, run_id):
        for _ in range(200):
            if mgr.get(run_id)["state"] in ("completed", "failed"):
                time.sleep(0.05)  # let the record be written just after the state flips
                return mgr.get(run_id)
            time.sleep(0.05)
        self.fail("run did not finish")


class Saving(RecordDirMixin, unittest.TestCase):
    def test_a_finished_investigation_is_saved_in_full(self):
        mgr = manager()
        run = self.finish(mgr, mgr.start("case-takeover"))
        rec = records.load_record(run["run_id"])
        r = rec["run"]
        self.assertEqual((r["state"], r["case_id"]), ("completed", "case-takeover"))
        self.assertEqual(r["final"]["simulated_action"], "REVIEW")
        self.assertTrue(r["events"] and r["evidence"] and r["run_header"])
        self.assertTrue(any(e["type"] == "behavior_profile" and e["payload"] for e in r["evidence"]))   # full payloads
        self.assertTrue(any(e["event_type"] == "model_turn" and "request_steps" in e["result_snapshot"] for e in r["events"]))
        self.assertEqual(r["alert"]["severity"], "high")
        self.assertEqual(rec["case"]["transaction"]["transaction_id"], "TX-1002")
        self.assertIn("not immutable", rec["notice"])

    def test_records_never_contain_credentials(self):
        mgr = manager()
        run = self.finish(mgr, mgr.start("case-familiar"))
        with open(os.path.join(self.dir, run["run_id"] + ".json"), encoding="utf-8") as f:
            blob = f.read().lower()
        for needle in ("api_key", "authorization", "bearer", "aiza", "x-goog"):
            self.assertNotIn(needle, blob)

    def test_experiment_runs_are_not_recorded_only_investigations(self):
        mgr = manager()
        exp = mgr.start_repeat("case-familiar", "end_to_end", 3)
        for _ in range(200):
            if mgr.get_experiment(exp)["state"] == "completed":
                break
            time.sleep(0.05)
        time.sleep(0.2)
        self.assertEqual(os.listdir(self.dir), [])

    def test_a_failed_investigation_is_recorded_too(self):
        from evidencetrail.gemini import GeminiClient
        mgr = RunManager(model_factory=GeminiClient, jev_factory=FakeJev, alert_store=AlertStore(":memory:"))
        run = self.finish(mgr, mgr.start("case-familiar"))
        rec = records.load_record(run["run_id"])["run"]
        self.assertEqual(rec["state"], "failed")
        self.assertIn("not configured", rec["failure"])

    def test_a_full_disk_never_breaks_the_investigation(self):
        blocker = os.path.join(self.dir, "blocked")
        open(blocker, "w").close()
        os.environ["EVIDENCETRAIL_RECORD_DIR"] = blocker       # a file where the folder should be
        mgr = manager()
        run = self.finish(mgr, mgr.start("case-familiar"))
        self.assertEqual(run["state"], "completed")
        self.assertIn("could not be written", run["record_error"])

    def test_no_half_written_files_are_left_behind(self):
        mgr = manager()
        self.finish(mgr, mgr.start("case-familiar"))
        self.assertTrue(all(n.endswith(".json") for n in os.listdir(self.dir)))


class AfterARestart(RecordDirMixin, unittest.TestCase):
    def _investigated(self):
        mgr = manager()
        run = self.finish(mgr, mgr.start("case-manipulated"))
        return run["run_id"], run

    def test_a_new_server_session_can_still_show_the_investigation(self):
        run_id, original = self._investigated()
        fresh = manager()                                       # a restarted server knows no runs in memory
        view = fresh.get(run_id)
        self.assertTrue(view["restored_from_record"])
        self.assertEqual(view["final"]["simulated_action"], original["final"]["simulated_action"])
        self.assertEqual(len(view["events"]), len(original["events"]))
        self.assertEqual(len(view["evidence"]), len(original["evidence"]))
        self.assertTrue(view["recorded_audit_trail_verified"])
        self.assertEqual(view["alert"]["alert_id"], original["alert"]["alert_id"])

    def test_the_full_record_export_works_after_a_restart(self):
        run_id, _ = self._investigated()
        api.set_manager(manager())
        status, export = api.handle_get(f"/api/investigations/{run_id}/export")
        self.assertEqual(status, 200)
        self.assertTrue(export["hash_chain_verified"])
        self.assertEqual(export["case_id"], "case-manipulated")

    def test_a_restored_investigation_is_read_only(self):
        run_id, _ = self._investigated()
        api.set_manager(manager())
        status, body = api.handle_post(f"/api/investigations/{run_id}/evaluate", {})
        self.assertEqual(status, 400)
        self.assertIn("saved record", body["error"])
        status, body = api.handle_post(f"/api/investigations/{run_id}/context-answer", {"answer": "yes"})
        self.assertEqual(status, 400)

    def test_unknown_or_malicious_ids_find_nothing(self):
        api.set_manager(manager())
        for bad in ("run-0000000000", "run-../../etc", "..", "run-XYZ"):
            self.assertEqual(api.handle_get(f"/api/investigations/{bad}")[0], 404)
        for bad in ("../x", "run-1", None, 5, ""):
            self.assertIsNone(records.load_record(bad))

    def test_a_corrupt_record_is_treated_as_missing(self):
        with open(os.path.join(self.dir, "run-aaaaaaaaaa.json"), "w") as f:
            f.write("{not json")
        self.assertIsNone(records.load_record("run-aaaaaaaaaa"))
        api.set_manager(manager())
        self.assertEqual(api.handle_get("/api/investigations/run-aaaaaaaaaa")[0], 404)


class StaysCurrent(RecordDirMixin, unittest.TestCase):
    def test_the_record_follows_later_changes_to_the_investigation(self):
        mgr = manager()
        api.set_manager(mgr)
        run = self.finish(mgr, mgr.start("case-manipulated"))
        self.assertEqual(records.load_record(run["run_id"])["run"]["final"]["simulated_action"], "CONTEXT_CHECK")
        status, _ = api.handle_post(f"/api/investigations/{run['run_id']}/context-answer", {"answer": "yes"})
        self.assertEqual(status, 200)
        self.assertEqual(records.load_record(run["run_id"])["run"]["final"]["simulated_action"], "REVIEW")
        status, _ = api.handle_post(f"/api/investigations/{run['run_id']}/evaluate", {})
        self.assertEqual(status, 202)
        for _ in range(200):
            saved = records.load_record(run["run_id"])["run"]["evaluation"]
            if saved and saved.get("state") != "running":
                break
            time.sleep(0.05)
        self.assertIn("geval", saved)                           # evaluation (here: unavailable, no keys) is kept too
        self.assertIn("deterministic", saved)


if __name__ == "__main__":
    unittest.main()
