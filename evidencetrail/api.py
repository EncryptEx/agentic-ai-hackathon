"""HTTP route logic for the host server. Each handler returns (status, json_body)."""

import re

from .alerts import SEVERITY_RANK, STATUSES
from .config import MAX_TOOL_CALLS
from .runs import RunManager
from .scenarios import list_scenarios

_manager = None  # created on first use so importing the module has no side effects
_RUN = re.compile(r"^/api/investigations/([\w-]+)(/evaluate|/context-answer|/export)?$")
_EXP = re.compile(r"^/api/experiments/([\w-]+)$")
_ALERT = re.compile(r"^/api/evidencetrail/alerts(?:/([\w-]+)(/status)?)?$")
_EXP_POST = ("/api/experiments/repeat", "/api/experiments/counterfactual", "/api/experiments/ablation")


def set_manager(manager):
    global _manager
    _manager = manager


def _mgr():
    global _manager
    if _manager is None:
        _manager = RunManager()
    return _manager


def handles(path):
    return path in ("/api/scenarios", "/api/investigations") or path.startswith(
        ("/api/investigations/", "/api/experiments/", "/api/evidencetrail/alerts"))


def _int(payload, key, default, lo, hi):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"'{key}' must be an integer between {lo} and {hi}")
    return value


def handle_get(path, query=None):
    query = query or {}
    m = _ALERT.match(path)
    if m and not m.group(2):
        if m.group(1):
            alert = _mgr().get_alert(m.group(1))
            return (200, alert) if alert else (404, {"error": "alert not found"})
        status = query.get("status", [None])[0]
        severity = query.get("severity", [None])[0]
        status = None if status in (None, "all") else status
        severity = None if severity in (None, "all") else severity
        if status is not None and status not in STATUSES:
            return 400, {"error": f"status must be one of {', '.join(STATUSES)} or 'all'"}
        if severity is not None and severity not in SEVERITY_RANK:
            return 400, {"error": "severity must be one of low, medium, high or 'all'"}
        alerts = _mgr().list_alerts(status=status, severity=severity)
        return 200, {"total": len(alerts), "alerts": alerts}
    if path == "/api/scenarios":
        return 200, {"scenarios": list_scenarios(), "max_tool_calls": MAX_TOOL_CALLS}
    m = _RUN.match(path)
    if m and m.group(2) == "/export":
        export = _mgr().export_run(m.group(1))
        return (200, export) if export else (404, {"error": "run not found"})
    if m and not m.group(2):
        run = _mgr().get(m.group(1))
        return (200, run) if run else (404, {"error": "run not found"})
    m = _EXP.match(path)
    if m:
        exp = _mgr().get_experiment(m.group(1))
        return (200, exp) if exp else (404, {"error": "experiment not found"})
    return 404, {"error": "Endpoint not found"}


def handle_post(path, payload):
    try:
        if path == "/api/investigations":
            run_id = _mgr().start(payload.get("caseId"), payload.get("configuration"))
            return 202, {"runId": run_id, "state": "queued"}
        if path == "/api/experiments/repeat":
            exp = _mgr().start_repeat(payload.get("caseId"), payload.get("mode", "end_to_end"),
                                        _int(payload, "repetitions", 5, 1, 20), payload.get("configuration"))
            return 202, {"experimentId": exp}
        if path == "/api/experiments/counterfactual":
            patch = payload.get("patch")
            if not isinstance(patch, dict):
                raise ValueError("'patch' must be an object")
            exp = _mgr().start_counterfactual(payload.get("caseId"), patch,
                                                _int(payload, "repetitions", 3, 1, 20))
            return 202, {"experimentId": exp}
        if path == "/api/experiments/ablation":
            case_ids = payload.get("caseIds")
            if case_ids is not None and (not isinstance(case_ids, list) or not case_ids):
                raise ValueError("'caseIds' must be a non-empty list")
            exp = _mgr().start_ablation(case_ids, _int(payload, "repetitions", 3, 1, 10))
            return 202, {"experimentId": exp}
        m = _ALERT.match(path)
        if m and m.group(1) and m.group(2) == "/status":
            note = payload.get("note")
            if note is not None and not isinstance(note, str):
                raise ValueError("'note' must be a string")
            alert = _mgr().set_alert_status(m.group(1), payload.get("status"), note)
            return (200, alert) if alert else (404, {"error": "alert not found"})
        m = _RUN.match(path)
        if m and m.group(2) == "/evaluate":
            if _mgr().get(m.group(1)) is None:
                return 404, {"error": "run not found"}
            evaluation = _mgr().start_evaluation(m.group(1), _int(payload, "repeats", 1, 1, 5))
            return 202, {"run_id": m.group(1), "evaluation": evaluation}
        if m and m.group(2) == "/context-answer":
            final = _mgr().answer_context_check(m.group(1), payload.get("answer"))
            return 200, {"final": final}
    except KeyError:
        return 404, {"error": "unknown case"}
    except NotImplementedError as e:
        return 501, {"error": str(e)}
    except (ValueError, TypeError) as e:
        return 400, {"error": str(e)}
    return 404, {"error": "Endpoint not found"}
