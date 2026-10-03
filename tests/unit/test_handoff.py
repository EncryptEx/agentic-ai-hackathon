"""Hand-off of an EvidenceTrail alert to the ADK specialist team (FastAPI adapter)."""

import asyncio
import os
import threading
import time
import unittest

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)
os.environ["EVIDENCETRAIL_ALERT_DB"] = ":memory:"

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.alert_feed  # noqa: F401  (needs google-adk)
    HAVE_STACK = True
except ImportError:  # pragma: no cover - the global interpreter may lack the ADK stack
    HAVE_STACK = False

from evidencetrail import api, handoff
from evidencetrail.alerts import AlertStore
from evidencetrail.runs import RunManager
from test_alerts import SUSPICIOUS, run
from test_evidencetrail import FakeJev

REPORT_TEXT = "FAKE ADK 11-SECTION REPORT"


class _Part:
    def __init__(self, text):
        self.text = text


class _Event:
    def __init__(self, text):
        self.content = type("C", (), {"parts": [_Part(text)]})()


class FakeSessions:
    async def create_session(self, app_name, user_id):
        return type("S", (), {"id": "sess-1"})()


class FakeRunner:
    def __init__(self, text=REPORT_TEXT, boom=None, gate=None):
        self.session_service, self.text, self.boom, self.gate = FakeSessions(), text, boom, gate
        self.prompts = []

    async def run_async(self, user_id, session_id, new_message):
        self.prompts.append(new_message.parts[0].text)
        if self.gate:
            while not self.gate.is_set():
                await asyncio.sleep(0.01)
        if self.boom:
            raise self.boom
        yield _Event("partial thought")
        yield _Event(self.text)


def _make_alert(store):
    _, r = run("case-takeover", FakeJev(triage=SUSPICIOUS))
    return store.create(r["alert"])


@unittest.skipUnless(HAVE_STACK, "FastAPI + ADK stack not installed")
class HandoffRoutes(unittest.TestCase):
    def setUp(self):
        self.store = AlertStore(":memory:")
        api.set_manager(RunManager(alert_store=self.store))
        self.alert = _make_alert(self.store)
        self.app = FastAPI()
        from evidencetrail.fastapi_routes import router
        self.app.include_router(router)
        self.app.state.agent_app_name = "app"

    def _client(self, runner):
        self.app.state.runner = runner
        return TestClient(self.app)

    def _wait(self, client, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            a = client.get(f"/api/evidencetrail/alerts/{self.alert['alert_id']}").json()
            if a["handoff"] and a["handoff"]["status"] != "running":
                return a
            time.sleep(0.05)
        self.fail("hand-off did not finish")

    def _post(self, client, body=None, alert_id=None):
        return client.post(f"/api/evidencetrail/alerts/{alert_id or self.alert['alert_id']}/handoff", json=body or {})

    def test_scenario_customer_not_in_framl_db_asks_for_a_customer_id(self):
        with self._client(FakeRunner()) as c:
            r = self._post(c)
        self.assertEqual(r.status_code, 409)
        self.assertTrue(r.json()["needs_customer_id"])
        self.assertIn("CUST-A102", r.json()["error"])
        self.assertIsNone(self.store.get(self.alert["alert_id"])["handoff"])  # nothing half-started

    def test_agent_report_is_attached_and_labelled_as_agent_written(self):
        runner = FakeRunner()
        with self._client(runner) as c:
            r = self._post(c, {"customerId": "cust-00001"})
            self.assertEqual(r.status_code, 202)
            a = self._wait(c)
        h = a["handoff"]
        self.assertEqual((h["status"], h["report_source"], h["customer_id"]), ("completed", "adk_agents", "CUST-00001"))
        self.assertTrue(h["customer_mismatch"])
        self.assertIn("does NOT appear in CUST-00001", runner.prompts[0])
        self.assertEqual(h["report"], REPORT_TEXT)  # last text part wins
        self.assertIsNone(h["adk_error"])
        self.assertIn("EVIDENCETRAIL", runner.prompts[0])
        self.assertIn(self.alert["title"], runner.prompts[0])
        self.assertIn("CUST-00001", runner.prompts[0])

    def test_handoff_never_changes_the_action_or_alert_status(self):
        with self._client(FakeRunner()) as c:
            self._post(c, {"customerId": "CUST-00001"})
            a = self._wait(c)
        self.assertEqual(a["policy"]["action"], self.alert["policy"]["action"])
        self.assertEqual((a["status"], a["severity"]), ("open", "high"))

    def test_when_the_agents_cannot_run_the_fallback_is_labelled_and_leaks_nothing(self):
        secret = "sk-secret-123"
        with self._client(FakeRunner(boom=RuntimeError(f"bad key {secret}"))) as c:
            self._post(c, {"customerId": "CUST-00001"})
            a = self._wait(c)
        h = a["handoff"]
        self.assertEqual((h["status"], h["report_source"], h["adk_error"]), ("completed", "specialist_tools_fallback", "RuntimeError"))
        self.assertIn("without an LLM", h["note"])
        self.assertTrue(h["report"].strip())
        self.assertNotIn(secret, str(a))

    def test_missing_runner_uses_the_labelled_fallback(self):
        with self._client(None) as c:
            self._post(c, {"customerId": "CUST-00001"})
            h = self._wait(c)["handoff"]
        self.assertEqual((h["report_source"], h["adk_error"]), ("specialist_tools_fallback", "NoRunner"))

    def test_a_second_handoff_while_running_is_rejected(self):
        gate = threading.Event()
        gate_async = FakeRunner(gate=gate)
        with self._client(gate_async) as c:
            self.assertEqual(self._post(c, {"customerId": "CUST-00001"}).status_code, 202)
            self.assertEqual(self._post(c, {"customerId": "CUST-00001"}).status_code, 409)
            gate.set()
            self.assertEqual(self._wait(c)["handoff"]["status"], "completed")

    def test_unexpected_failure_leaves_a_visible_failed_state_not_a_stuck_running_one(self):
        original = handoff.execute

        async def boom(*a, **k):
            raise ValueError("kaboom")
        handoff.execute = boom
        try:
            with self._client(FakeRunner()) as c:
                self._post(c, {"customerId": "CUST-00001"})
                a = self._wait(c)
        finally:
            handoff.execute = original
        self.assertEqual((a["handoff"]["status"], a["handoff"]["error"]), ("failed", "ValueError"))

    def test_validation_and_unknown_alert(self):
        with self._client(FakeRunner()) as c:
            self.assertEqual(self._post(c, alert_id="ALT-NOPE").status_code, 404)
            self.assertEqual(self._post(c, {"customerId": 5}).status_code, 400)
            bad = c.post(f"/api/evidencetrail/alerts/{self.alert['alert_id']}/handoff", content=b"{not json",
                         headers={"Content-Type": "application/json"})
            self.assertEqual(bad.status_code, 400)

    def test_other_alert_routes_still_work_through_the_adapter(self):
        with self._client(FakeRunner()) as c:
            self.assertEqual(c.get("/api/evidencetrail/alerts", params={"status": "all"}).json()["total"], 1)
            r = c.post(f"/api/evidencetrail/alerts/{self.alert['alert_id']}/status", json={"status": "acknowledged"})
            self.assertEqual(r.json()["status"], "acknowledged")


class HandoffMapping(unittest.TestCase):
    def test_trigger_alert_carries_the_evidencetrail_context(self):
        _, r = run("case-takeover", FakeJev(triage=SUSPICIOUS))
        t = handoff.trigger_alert(r["alert"])
        self.assertEqual((t["rule_id"], t["severity"]), ("EVIDENCETRAIL", "HIGH"))
        for fragment in (r["alert"]["alert_id"], "TX-1002", "8000 SEK", "RCP-601", "REVIEW"):
            self.assertIn(fragment, t["summary"])

    def test_a_manually_chosen_customer_is_not_passed_off_as_the_transfers_owner(self):
        _, r = run("case-takeover", FakeJev(triage=SUSPICIOUS))
        a = r["alert"]
        same = handoff.trigger_alert(a, a["transaction"]["customer_id"])
        other = handoff.trigger_alert(a, "cust-00015")
        self.assertNotIn("IMPORTANT", same["summary"])
        self.assertIn("does NOT appear in CUST-00015", other["summary"])
        self.assertIn("CUST-A102", other["summary"])
        self.assertIn("Do not attribute", other["summary"])
        self.assertFalse(handoff.customer_mismatch(a, "CUST-A102"))
        self.assertTrue(handoff.customer_mismatch(a, "CUST-00015"))
        self.assertFalse(handoff.customer_mismatch(a, None))

    def test_legacy_server_reports_that_handoff_needs_the_combined_server(self):
        api.set_manager(RunManager(alert_store=AlertStore(":memory:")))
        self.assertEqual(api.handle_post("/api/evidencetrail/alerts/ALT-1/handoff", {})[0], 501)

    def test_alert_store_persists_the_handoff_record(self):
        store = AlertStore(":memory:")
        a = _make_alert(store)
        self.assertIsNone(a["handoff"])
        store.set_handoff(a["alert_id"], {"status": "completed", "report": "x"})
        self.assertEqual(store.get(a["alert_id"])["handoff"]["report"], "x")
        self.assertIsNone(store.set_handoff("ALT-NOPE", {}))


if __name__ == "__main__":
    unittest.main()
