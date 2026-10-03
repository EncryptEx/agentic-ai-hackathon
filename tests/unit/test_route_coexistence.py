"""EvidenceTrail and the audit ledger both live under /api/investigations. Neither may shadow the other.

Regression: EvidenceTrail used to claim /api/investigations/{anything}, which swallowed the audit ledger's
/audit-trail, /sign-off and /{investigation id} routes (the Audit Trail tab then failed to load).
"""

import unittest

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:  # pragma: no cover - the global interpreter may lack FastAPI
    HAVE_FASTAPI = False

if HAVE_FASTAPI:
    from evidencetrail import api
    from evidencetrail.alerts import AlertStore
    from evidencetrail.fastapi_routes import router
    from evidencetrail.runs import RunManager
    from fakes import FakeJev, TeamAndDecider


def stand_in_ledger_routes(app):
    """Same paths and shapes as the audit ledger in app/fast_api_app.py, registered AFTER our router."""
    @app.get("/api/investigations/audit-trail")
    async def audit_trail():
        return [{"investigation_id": "INV-AAA"}]

    @app.post("/api/investigations/sign-off")
    async def sign_off():
        return {"signed": True}

    @app.get("/api/investigations/{investigation_id}")
    async def detail(investigation_id: str):
        return {"investigation_id": investigation_id, "from": "ledger"}


@unittest.skipUnless(HAVE_FASTAPI, "FastAPI not installed")
class Coexistence(unittest.TestCase):
    def _client(self, ledger_first=False):
        api.set_manager(RunManager(model_factory=TeamAndDecider, jev_factory=FakeJev, alert_store=AlertStore(":memory:")))
        app = FastAPI()
        if ledger_first:
            stand_in_ledger_routes(app)
        app.include_router(router)
        if not ledger_first:
            stand_in_ledger_routes(app)
        return TestClient(app)

    def test_the_ledger_routes_are_reachable_whatever_the_registration_order(self):
        for ledger_first in (False, True):
            c = self._client(ledger_first)
            self.assertEqual(c.get("/api/investigations/audit-trail").json(), [{"investigation_id": "INV-AAA"}], ledger_first)
            self.assertEqual(c.post("/api/investigations/sign-off", json={}).json(), {"signed": True}, ledger_first)
            self.assertEqual(c.get("/api/investigations/INV-123").json()["from"], "ledger", ledger_first)

    def test_evidencetrail_run_ids_still_reach_evidencetrail(self):
        c = self._client()
        started = c.post("/api/investigations", json={"caseId": "case-familiar"})
        self.assertEqual(started.status_code, 202)
        run_id = started.json()["runId"]
        self.assertRegex(run_id, r"^run-[0-9a-f]{10}$")
        self.assertEqual(c.get(f"/api/investigations/{run_id}").json()["run_id"], run_id)
        self.assertEqual(c.get(f"/api/investigations/{run_id}/export").status_code in (200, 404), True)
        self.assertEqual(c.post(f"/api/investigations/{run_id}/context-answer", json={"answer": "yes"}).status_code in (200, 400), True)
        self.assertEqual(c.get("/api/investigations/run-0000000000").json(), {"error": "run not found"})

    def test_ids_that_merely_look_similar_go_to_the_ledger_not_to_us(self):
        c = self._client()
        for look_alike in ("run-123", "run-ZZZZZZZZZZ", "run-0000000000x", "runs-0000000000", "audit-trail-x"):
            self.assertEqual(c.get(f"/api/investigations/{look_alike}").json().get("from"), "ledger", look_alike)


@unittest.skipUnless(HAVE_FASTAPI, "FastAPI not installed")
class RealCombinedApp(unittest.TestCase):
    """Against the actual app, so this fails if either side ever claims the other's URLs."""

    @classmethod
    def setUpClass(cls):
        try:
            from app.fast_api_app import app
        except ImportError as e:  # pragma: no cover - needs the ADK stack
            raise unittest.SkipTest(f"combined app needs the ADK stack: {e}")
        cls.client = TestClient(app)  # no lifespan: only routing is exercised

    def test_the_real_audit_ledger_routes_still_answer(self):
        r = self.client.get("/api/investigations/audit-trail?limit=3")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)             # the Audit tab calls .map() on this
        self.assertEqual(self.client.get("/api/investigations/INV-DOES-NOT-EXIST").json()["detail"], "Investigation not found")
        self.assertEqual(self.client.post("/api/investigations/sign-off", json={}).status_code, 422)  # their schema, not ours

    def test_evidencetrail_still_answers_in_the_same_app(self):
        self.assertEqual(self.client.get("/api/investigations/run-0000000000").json(), {"error": "run not found"})
        self.assertEqual(self.client.get("/api/scenarios").status_code, 200)


if __name__ == "__main__":
    unittest.main()
