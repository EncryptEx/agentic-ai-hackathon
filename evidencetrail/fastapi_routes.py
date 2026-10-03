"""FastAPI adapter for the EvidenceTrail API.

The route logic lives in evidencetrail.api (framework-agnostic), so the same handlers serve both
the legacy zero-dependency server (web/server.py) and the combined FastAPI app (app/fast_api_app.py).
The ADK hand-off lives here because it needs the app's ADK runner.
"""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import api, handoff
from .canon import now_utc

router = APIRouter()
_tasks = set()  # keep references so background hand-offs are not garbage collected mid-run


def _respond(result):
    status, body = result
    return JSONResponse(body, status_code=status)


def _query(request: Request):
    """Same shape as urllib.parse.parse_qs: {key: [values]}."""
    out = {}
    for key, value in request.query_params.multi_items():
        out.setdefault(key, []).append(value)
    return out


async def _json_body(request: Request):
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError as e:
        return None, JSONResponse({"error": f"Invalid JSON payload: {e}"}, status_code=400)
    if not isinstance(payload, dict):
        return None, JSONResponse({"error": "JSON body must be an object"}, status_code=400)
    return payload, None


@router.get("/api/scenarios")
@router.get("/api/evidencetrail/seed/transactions")
@router.get("/api/investigations/{rest:path}")
@router.get("/api/experiments/{rest:path}")
@router.get("/api/evidencetrail/alerts")
@router.get("/api/evidencetrail/alerts/{rest:path}")
async def evidencetrail_get(request: Request):
    return _respond(api.handle_get(request.url.path, _query(request)))


@router.post("/api/evidencetrail/alerts/{alert_id}/handoff")
async def evidencetrail_handoff(alert_id: str, request: Request):
    """Hand the alert's customer to the ADK specialist team. Runs in the background; poll the alert."""
    payload, error = await _json_body(request)
    if error:
        return error
    mgr = api._mgr()
    alert = mgr.get_alert(alert_id)
    if alert is None:
        return JSONResponse({"error": "alert not found"}, status_code=404)
    current = alert.get("handoff") or {}
    if current.get("status") == "running":
        return JSONResponse({"error": "a hand-off is already running for this alert"}, status_code=409)
    customer_id = payload.get("customerId")
    if customer_id is not None and not isinstance(customer_id, str):
        return JSONResponse({"error": "'customerId' must be a string"}, status_code=400)
    try:
        cust, packet, prompt = await asyncio.to_thread(handoff.prepare, alert, customer_id)
    except handoff.CustomerNotFound:
        who = (customer_id or alert["transaction"]["customer_id"]).upper()
        return JSONResponse({
            "error": (f"Customer {who} is not in the FRAML database the ADK team reads from. EvidenceTrail "
                      "scenario customers are separate synthetic records; send a customerId from the FRAML "
                      "database (for example CUST-00015)."),
            "needs_customer_id": True}, status_code=409)
    except ImportError:
        return JSONResponse({"error": "The ADK investigation team is not installed on this server."}, status_code=501)

    record = {"status": "running", "customer_id": cust, "started_at": now_utc()}
    mgr.set_alert_handoff(alert_id, record)
    runner = getattr(request.app.state, "runner", None)
    app_name = getattr(request.app.state, "agent_app_name", "app")

    async def work():
        try:
            result = await handoff.execute(alert, cust, packet, prompt, runner, app_name)
            result["started_at"] = record["started_at"]
        except Exception as e:  # leave a visible failure on the alert instead of a stuck "running"
            result = {"status": "failed", "customer_id": cust, "started_at": record["started_at"],
                      "error": f"{type(e).__name__}", "completed_at": now_utc()}
        mgr.set_alert_handoff(alert_id, result)

    task = asyncio.create_task(work())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return JSONResponse({"alert_id": alert_id, "handoff": record}, status_code=202)


@router.post("/api/investigations")
@router.post("/api/investigations/{rest:path}")
@router.post("/api/experiments/{rest:path}")
@router.post("/api/evidencetrail/alerts/{rest:path}")
async def evidencetrail_post(request: Request):
    payload, error = await _json_body(request)
    if error:
        return error
    return _respond(api.handle_post(request.url.path, payload))
