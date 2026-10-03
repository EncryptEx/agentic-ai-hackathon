"""Regression tests for the Jev -> human validation -> ADK workflow gate."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import fast_api_app as api


def _case(case_id="TX-HITL-1"):
    return {
        "case_id": case_id,
        "tx_id": case_id,
        "customer_id": "CUST-00015",
        "row": {
            "transaction_id": case_id,
            "customer_id": "CUST-00015",
            "amount_usd": "9500",
            "currency": "USD",
        },
        "status": "pending_validation",
        "jev": {"suspicion": "SUSPICIOUS", "severity": 2},
        "created_at": "2026-10-03T10:00:00Z",
        "synthetic": True,
    }


class _Socket:
    def __init__(self):
        self.messages = []

    async def send_text(self, message):
        self.messages.append(json.loads(message))


def setup_function():
    api.REALTIME_INVESTIGATIONS.clear()
    api._TRIAGE_RESULTS.clear()
    api._TRIAGE_INFLIGHT.clear()


def teardown_function():
    api.REALTIME_INVESTIGATIONS.clear()
    api._TRIAGE_RESULTS.clear()
    api._TRIAGE_INFLIGHT.clear()


def test_suspicious_jev_result_stops_at_manual_gate():
    row = _case()["row"]
    socket = _Socket()
    assessment = {
        "status": "ok",
        "suspicion": "SUSPICIOUS",
        "severity": 2,
        "raw": {"model": "jev-test"},
    }

    with patch.object(api, "_assess_transaction_with_jev", AsyncMock(return_value=assessment)), patch.object(
        api, "run_investigation_for_realtime", AsyncMock()
    ) as run_adk:
        asyncio.run(api.triage_transaction(row, None, "app", socket))

    queued = api.REALTIME_INVESTIGATIONS[row["transaction_id"]]
    assert queued["status"] == "pending_validation"
    assert socket.messages[-1]["case"]["status"] == "pending_validation"
    run_adk.assert_not_awaited()


def test_reject_never_starts_adk():
    api.REALTIME_INVESTIGATIONS["TX-HITL-1"] = _case()
    with TestClient(api.app) as client, patch.object(
        api, "run_investigation_for_realtime", AsyncMock()
    ) as run_adk:
        response = client.post(
            "/api/realtime/investigations/TX-HITL-1/decision",
            json={"decision": "REJECT", "investigator": "Ana Analyst", "notes": "False positive"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "rejected"
    assert response.json()["human_validation"]["investigator"] == "Ana Analyst"
    run_adk.assert_not_awaited()


def test_approval_starts_full_workflow_once():
    api.REALTIME_INVESTIGATIONS["TX-HITL-1"] = _case()
    run_adk = AsyncMock()
    with TestClient(api.app) as client, patch.object(api, "run_investigation_for_realtime", run_adk):
        payload = {"decision": "APPROVE", "investigator": "Ana Analyst", "notes": "Escalate"}
        first = client.post("/api/realtime/investigations/TX-HITL-1/decision", json=payload)
        second = client.post("/api/realtime/investigations/TX-HITL-1/decision", json=payload)

    assert first.status_code == 202
    assert first.json()["status"] == "running"
    assert second.status_code == 202
    assert run_adk.await_count == 1


def test_approved_case_collects_the_adk_runner_report():
    class SessionService:
        async def create_session(self, **_kwargs):
            return SimpleNamespace(id="session-hitl")

    class FakeRunner:
        session_service = SessionService()

        def __init__(self):
            self.messages = []

        async def run_async(self, **kwargs):
            self.messages.append(kwargs["new_message"].parts[0].text)
            yield SimpleNamespace(
                content=SimpleNamespace(parts=[SimpleNamespace(text="Consolidated ADK report")])
            )

    api.REALTIME_INVESTIGATIONS["TX-HITL-1"] = {
        **_case(),
        "status": "running",
        "human_validation": {"decision": "APPROVE", "investigator": "Ana Analyst"},
    }
    runner = FakeRunner()
    with patch.object(api.manager, "broadcast", AsyncMock()):
        asyncio.run(
            api.run_investigation_for_realtime(
                "CUST-00015", _case()["row"], runner, "app", "TX-HITL-1"
            )
        )

    completed = api.REALTIME_INVESTIGATIONS["TX-HITL-1"]
    assert completed["status"] == "completed"
    assert completed["report"] == "Consolidated ADK report"
    assert completed["workflow_source"] == "adk_agents"
    assert completed["adk_error"] is None
    assert "JEV-REALTIME" in runner.messages[0]
    assert "TX-HITL-1" in runner.messages[0]
    assert "Ana Analyst approved" in runner.messages[0]


def test_investigator_name_is_required():
    api.REALTIME_INVESTIGATIONS["TX-HITL-1"] = _case()
    response = TestClient(api.app).post(
        "/api/realtime/investigations/TX-HITL-1/decision",
        json={"decision": "APPROVE", "investigator": "", "notes": ""},
    )
    assert response.status_code == 400
    assert api.REALTIME_INVESTIGATIONS["TX-HITL-1"]["status"] == "pending_validation"


def test_investigator_page_exposes_real_validation_controls():
    response = TestClient(api.app).get("/investigator")
    assert response.status_code == 200
    assert "Approve &amp; run ADK workflow" not in response.text
    assert "Approve & run ADK workflow" in response.text
    assert "/api/realtime/investigations/" in response.text
