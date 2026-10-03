"""HTTP route logic for the host server. Each handler returns (status, json_body)."""

import re

from .config import MAX_TOOL_CALLS
from .runs import RunManager
from .scenarios import list_scenarios

_manager = RunManager()
_RUN = re.compile(r"^/api/investigations/([\w-]+)(/evaluate|/context-answer|/export)?$")
_EXP = re.compile(r"^/api/experiments/([\w-]+)$")
_EXP_POST = ("/api/experiments/repeat", "/api/experiments/counterfactual", "/api/experiments/ablation")


def set_manager(manager):
    global _manager
    _manager = manager


def handles(path):
    return path in ("/api/scenarios", "/api/investigations") or path.startswith(
        ("/api/investigations/", "/api/experiments/"))


def _int(payload, key, default, lo, hi):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"'{key}' must be an integer between {lo} and {hi}")
    return value


def handle_get(path):
    if path == "/api/scenarios":
        return 200, {"scenarios": list_scenarios(), "max_tool_calls": MAX_TOOL_CALLS}
    m = _RUN.match(path)
    if m and m.group(2) == "/export":
        export = _manager.export_run(m.group(1))
        return (200, export) if export else (404, {"error": "run not found"})
    if m and not m.group(2):
        run = _manager.get(m.group(1))
        return (200, run) if run else (404, {"error": "run not found"})
    m = _EXP.match(path)
    if m:
        exp = _manager.get_experiment(m.group(1))
        return (200, exp) if exp else (404, {"error": "experiment not found"})
    return 404, {"error": "Endpoint not found"}


def handle_post(path, payload):
    try:
        if path == "/api/investigations":
            run_id = _manager.start(payload.get("caseId"), payload.get("configuration"))
            return 202, {"runId": run_id, "state": "queued"}
        if path == "/api/experiments/repeat":
            exp = _manager.start_repeat(payload.get("caseId"), payload.get("mode", "end_to_end"),
                                        _int(payload, "repetitions", 5, 1, 20), payload.get("configuration"))
            return 202, {"experimentId": exp}
        if path == "/api/experiments/counterfactual":
            patch = payload.get("patch")
            if not isinstance(patch, dict):
                raise ValueError("'patch' must be an object")
            exp = _manager.start_counterfactual(payload.get("caseId"), patch,
                                                _int(payload, "repetitions", 3, 1, 20))
            return 202, {"experimentId": exp}
        if path == "/api/experiments/ablation":
            case_ids = payload.get("caseIds")
            if case_ids is not None and (not isinstance(case_ids, list) or not case_ids):
                raise ValueError("'caseIds' must be a non-empty list")
            exp = _manager.start_ablation(case_ids, _int(payload, "repetitions", 3, 1, 10))
            return 202, {"experimentId": exp}
        m = _RUN.match(path)
        if m and m.group(2) == "/evaluate":
            if _manager.get(m.group(1)) is None:
                return 404, {"error": "run not found"}
            evaluation = _manager.start_evaluation(m.group(1), _int(payload, "repeats", 1, 1, 5))
            return 202, {"run_id": m.group(1), "evaluation": evaluation}
        if m and m.group(2) == "/context-answer":
            final = _manager.answer_context_check(m.group(1), payload.get("answer"))
            return 200, {"final": final}
    except KeyError:
        return 404, {"error": "unknown case"}
    except NotImplementedError as e:
        return 501, {"error": str(e)}
    except (ValueError, TypeError) as e:
        return 400, {"error": str(e)}
    return 404, {"error": "Endpoint not found"}
