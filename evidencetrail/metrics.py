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
        "failures": [{"run_id": r["run_id"], "state": r["state"],
                      "reason": r.get("failure") or r.get("error") or (r.get("final") or {}).get("explanation")}
                     for r in finished if r["state"] != "completed"],
        "error_counts": [_error_count(r) for r in finished],
        "usage_totals": _usage_totals(finished),
        "context_compression": summarize_context(finished),
        "cost": "not computed: provider rates are not configured",
        "note": ("Agreement can be consistently wrong; five synthetic cases do not establish "
                 "precision, recall or calibration."),
    }


def _error_count(run):
    return sum(1 for e in run.get("events", []) if e["event_type"] in ("tool_error", "run_failed"))


def summarize_context(runs):
    """Request bytes are measured; they are not Gemini token counts or cost savings."""
    totals = {name: 0 for name in ("before_bytes", "after_bytes", "api_calls", "cache_hits",
                                 "accepted", "rejected", "duration_ms")}
    statuses = Counter()
    for run in runs:
        for event in run.get("events", []):
            stats = (event.get("result_snapshot") or {}).get("context_compression")
            if not isinstance(stats, dict):
                continue
            statuses[stats.get("status", "unknown")] += 1
            for name in totals:
                totals[name] += stats.get(name, 0)
    totals["statuses"] = dict(statuses)
    totals["byte_reduction_fraction"] = (
        1 - totals["after_bytes"] / totals["before_bytes"] if totals["before_bytes"] else None)
    totals["note"] = "Request byte reduction, not token or monetary savings; compare provider usage separately."
    return totals


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
    base_id = run["case_id"][:-3] if run["case_id"].endswith("-cf") else run["case_id"]
    expected = EXPECTED_ACTIONS.get(base_id)
    seed_check = _seed_check(base_id, final)
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
        "seed_check": seed_check,
    }


def _seed_check(case_id, final):
    """For seed transactions: compare the system's outcome with the generator's answer key (evaluator only)."""
    from . import seed as _seed
    if not _seed.is_seed_case(case_id):
        return None
    from .seed_labels import ground_truth
    truth = ground_truth(case_id[len(_seed.CASE_PREFIX):])
    if truth is None or not final:
        return None
    flagged_by_system = final.get("simulated_action") not in (None, "ALLOW")
    return {"seed_tag": truth["tag"], "seed_flagged": truth["flagged"], "system_flagged": flagged_by_system,
            "agrees": truth["flagged"] == flagged_by_system,
            "note": "Seed generator tag (an answer key the agents never see). Not real-world accuracy."}
