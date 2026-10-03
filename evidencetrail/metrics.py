"""Repeatability and deterministic evaluation metrics. No invented percentages."""

from collections import Counter

from .eval_fixtures import EXPECTED_ACTIONS


def modal_agreement(actions):
    """Most frequent action count over successful runs, with raw counts."""
    counts = Counter(actions)
    n = len(actions)
    if n == 0:
        return {"successful_runs": 0, "modal_action": None, "modal_count": 0, "counts": {}}
    action, count = counts.most_common(1)[0]
    return {"successful_runs": n, "modal_action": action, "modal_count": count,
            "agreement": f"{count}/{n}", "counts": dict(counts)}


def pairwise_agreement(actions):
    """sum_a n_a(n_a-1) / (N(N-1)); needs N >= 2 successful runs."""
    n = len(actions)
    if n < 2:
        return None
    return sum(c * (c - 1) for c in Counter(actions).values()) / (n * (n - 1))


def summarize_runs(runs):
    attempted = len(runs)
    finished = [r for r in runs if r["state"] in ("completed", "failed")]
    ok = [r for r in finished if r["state"] == "completed" and r.get("final")
          and r["final"]["status"] == "COMPLETE"]
    actions = [r["final"]["simulated_action"] for r in ok]
    counts = {a: actions.count(a) for a in ("ALLOW", "CONTEXT_CHECK", "REVIEW")}
    sequences = Counter(" > ".join(e["tool_name"] for e in r["events"]
                                   if e["event_type"] in ("tool_call", "tool_error")) for r in ok)
    consult_sequences = Counter(" > ".join(e["validated_arguments"]["specialist"] for e in r["events"]
                                           if e["event_type"] == "consultation") for r in ok)
    return {
        "attempted_runs": attempted, "finished_runs": len(finished), "successful_runs": len(ok),
        "failed_or_incomplete_runs": len(finished) - len(ok),
        "action_counts": counts, "modal": modal_agreement(actions),
        "pairwise_agreement": pairwise_agreement(actions),
        "opposite_outcome_flag": counts["ALLOW"] > 0 and counts["REVIEW"] > 0,
        "tool_sequences": dict(sequences),
        "specialist_sequences": dict(consult_sequences),
        "architectures": sorted({r.get("architecture") for r in finished if r.get("architecture")}),
        "tool_call_counts": [r.get("tool_call_count") for r in finished],
        "elapsed_ms": [r.get("elapsed_ms") for r in finished],
        "error_counts": [_error_count(r) for r in finished],
        "usage_totals": _usage_totals(finished),
        "cost": "not computed: provider rates are not configured",
        "note": ("Agreement can be consistently wrong; five synthetic cases do not establish "
                 "precision, recall or calibration."),
    }


def _error_count(run):
    return sum(1 for e in run.get("events", []) if e["event_type"] in ("tool_error", "run_failed"))


def _usage_totals(runs):
    """Sum numeric usage fields the provider actually reported; empty if none were reported."""
    totals = {}
    for r in runs:
        for e in r.get("events", []):
            usage = e.get("usage_if_available")
            if isinstance(usage, dict):
                for k, v in usage.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        totals[k] = totals.get(k, 0) + v
    return totals


def deterministic_checks(run):
    """Policy-label match, reference validity and trace facts. Labels never reach the agent."""
    final = run.get("final") or {}
    expected = EXPECTED_ACTIONS.get(run["case_id"].replace("-cf", ""))
    # Labels describe the decision before any simulated customer answer.
    compared = final.get("action_before_context_answer") or final.get("simulated_action")
    validity = final.get("reference_validity")
    elapsed = sum((e.get("duration_ms") or 0) for e in run.get("events", []))
    return {
        "expected_action": expected,
        "simulated_action": final.get("simulated_action"),
        "action_compared": compared,
        "policy_label_match": None if expected is None else compared == expected,
        "label_status": "illustrative policy label on a synthetic case, not real-world accuracy",
        "reference_validity": validity,
        "reference_validity_note": "Valid IDs do not establish semantic support.",
        "tool_call_count": run.get("tool_call_count"),
        "error_count": sum(1 for e in run.get("events", []) if e["event_type"] in ("tool_error", "run_failed")),
        "elapsed_ms_recorded": elapsed,
    }
