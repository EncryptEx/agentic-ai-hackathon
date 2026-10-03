"""FastAPI adapter for the EvidenceTrail API.

The route logic lives in evidencetrail.api (framework-agnostic), so the same handlers serve both
the legacy zero-dependency server (web/server.py) and the combined FastAPI app (app/fast_api_app.py).
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import api

router = APIRouter()


def _respond(result):
    status, body = result
    return JSONResponse(body, status_code=status)


def _query(request: Request):
    """Same shape as urllib.parse.parse_qs: {key: [values]}."""
    out = {}
    for key, value in request.query_params.multi_items():
        out.setdefault(key, []).append(value)
    return out


@router.get("/api/scenarios")
@router.get("/api/investigations/{rest:path}")
@router.get("/api/experiments/{rest:path}")
@router.get("/api/evidencetrail/alerts")
@router.get("/api/evidencetrail/alerts/{rest:path}")
async def evidencetrail_get(request: Request):
    return _respond(api.handle_get(request.url.path, _query(request)))


@router.post("/api/investigations")
@router.post("/api/investigations/{rest:path}")
@router.post("/api/experiments/{rest:path}")
@router.post("/api/evidencetrail/alerts/{rest:path}")
async def evidencetrail_post(request: Request):
    raw = await request.body()
    try:
        import json
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError as e:
        return JSONResponse({"error": f"Invalid JSON payload: {e}"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "JSON body must be an object"}, status_code=400)
    return _respond(api.handle_post(request.url.path, payload))
