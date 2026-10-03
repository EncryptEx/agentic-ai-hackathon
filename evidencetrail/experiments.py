"""Experiments beyond plain repeats: fixed-evidence judgment (B) and ablation (E).

Everything here uses the same prompts, tool budget and deterministic policy as the agent;
only the stated component varies. Results report raw counts and failures, never invented
percentages. Labels come from eval_fixtures and are illustrative policy labels on synthetic
cases, not evidence of real-world accuracy.
"""

import json
import time

from . import policy
from .agent import SYSTEM_PROMPT, _validate_finish
from .canon import sha256
from .config import MAX_GRAPH_HOPS
from .eval_fixtures import EXPECTED_ACTIONS
from .evidence import EvidenceStore
from .jev import ProviderUnavailable, build_state
from .metrics import modal_agreement, pairwise_agreement, summarize_runs
from .tools import FINISH, TOOL_DECLARATIONS, ToolError, execute_data_tool

_DATA_PLAN = (("get_behavior_profile", lambda tx: {"customer_id": tx["customer_id"]}),
              ("inspect_device", lambda tx: {"transaction_id": tx["transaction_id"]}),
              ("inspect_recipient", lambda tx: {"recipient_id": tx["recipient_id"]}),
              ("search_relationship_graph",
               lambda tx: {"recipient_id": tx["recipient_id"], "max_hops": MAX_GRAPH_HOPS}))
_FINISH_DECL = [d for d in TOOL_DECLARATIONS if d["name"] == FINISH]


def gather_all(case):
    """Run every data tool once in a fixed order. Failures become visible tool_error evidence."""
    store = EvidenceStore()
    for name, build in _DATA_PLAN:
        try:
            type_, record_id, payload = execute_data_tool(name, build(case["transaction"]), case)
            store.add(type_, name, record_id, payload)
        except ToolError as e:
            store.add("tool_error", name, None, {"tool": name, "error": str(e),
                                                 "note": "Missing evidence, not reassuring evidence."})
    return store


def rules_baseline(case):
    """Deterministic arm: gather all evidence, apply policy v1. No model, no Jev."""
    store = gather_all(case)
    cited = [e["evidence_id"] for e in store.all() if e["type"] != "tool_error"]
    finish = {"recommended_action": "ALLOW", "status": "COMPLETE", "remaining_uncertainty": "n/a (rules arm)",
              "claims": [{"text": "Policy v1 applied to all recorded evidence.", "supporting_evidence_ids": cited}]}
    final = policy.decide(store, case["transaction"], finish)
    final["agent_recommendation"] = None  # no agent in this arm
    return {"arm": "rules", "final": final, "evidence": store.all(), "tool_call_count": len(_DATA_PLAN)}


def _bundle_hash(store):
    return sha256([e["snapshot_hash"] for e in store.all()])


def _decision_prompt(case, store):
    return json.dumps({
        "task": ("The evidence bundle below is frozen. No further tools are available. "
                 "Submit finish_investigation with claims citing these evidence IDs."),
        "transaction": case["transaction"],
        "evidence": [{"evidence_id": e["evidence_id"], "type": e["type"], "source": e["source"],
                      "payload": e["payload"]} for e in store.all()]}, sort_keys=True)


def _jev_state(store):
    return build_state([e for e in store.all() if e["type"] not in ("tool_error", "jev_assessment", "alert_triage")])


def _summarize_values(values):
    if not values:
        return {"successful": 0}
    if all(isinstance(v, str) for v in values):
        return {"successful": len(values), **modal_agreement(values)}
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(nums) == len(values):
        return {"successful": len(nums), "min": min(nums), "max": max(nums), "mean": sum(nums) / len(nums)}
    return {"successful": len(values), "values": values}


def fixed_evidence_experiment(case, model, jev, repetitions, on_progress=None):
    """Experiment B: freeze one evidence bundle; call the Gemini decision and Jev assessment
    independently `repetitions` times and compare their outputs separately."""
    store = gather_all(case)
    decisions, jev_runs = [], []
    for i in range(repetitions):
        t0 = time.monotonic()
        row = {"attempt": i + 1}
        try:
            turn = model.generate(SYSTEM_PROMPT, [{"type": "user_input", "content": _decision_prompt(case, store)}],
                                  _FINISH_DECL)
            call = next((c for c in turn.calls if c["name"] == FINISH), None)
            if call is None:
                raise ToolError("model did not call finish_investigation")
            final = policy.decide(store, case["transaction"], _validate_finish(call["arguments"]))
            row.update(status=final["status"], action=final["simulated_action"], rule=final["rule"],
                       agent_action=final["agent_recommendation"]["recommended_action"],
                       returned_model_version=turn.returned_model_version)
        except (ProviderUnavailable, ToolError) as e:
            row.update(status="ERROR", error=str(e))
        row["duration_ms"] = int((time.monotonic() - t0) * 1000)
        decisions.append(row)

        t0 = time.monotonic()
        jrow = {"attempt": i + 1}
        try:
            result = jev.assess(_jev_state(store))
            jrow.update(status="OK", normalized=result["normalized"], model=result["model"], raw=result["raw"])
        except ProviderUnavailable as e:
            jrow.update(status="ERROR", error=str(e))
        jrow["duration_ms"] = int((time.monotonic() - t0) * 1000)
        jev_runs.append(jrow)
        if on_progress:
            on_progress(i + 1)

    ok = [d["action"] for d in decisions if d["status"] == "COMPLETE"]
    jev_ok = [r for r in jev_runs if r["status"] == "OK"]
    questions = sorted({q for r in jev_ok for q in r["normalized"]})
    return {
        "kind": "fixed_evidence",
        "bundle": {"evidence_ids": store.ids(), "bundle_hash": _bundle_hash(store)},
        "decision": {"attempted": repetitions, "successful": len(ok),
                     "incomplete_or_error": repetitions - len(ok),
                     "action_counts": {a: ok.count(a) for a in ("ALLOW", "CONTEXT_CHECK", "REVIEW")},
                     "modal": modal_agreement(ok), "pairwise_agreement": pairwise_agreement(ok),
                     "runs": decisions},
        "jev": {"attempted": repetitions, "successful": len(jev_ok), "errors": repetitions - len(jev_ok),
                "per_question": {q: _summarize_values([r["normalized"][q] for r in jev_ok if q in r["normalized"]])
                                 for q in questions},
                "runs": [{k: v for k, v in r.items() if k != "raw"} for r in jev_runs]},
        "note": ("Decision and Jev outputs are compared separately. Agreement can be consistently wrong; "
                 "no probabilities here are calibrated."),
    }


def summarize_ablation(exp, runs_by_id, rules_results):
    """Per-arm, per-case results with raw counts. Labels are illustrative, on synthetic cases."""
    out = {"kind": "ablation", "arms": {}, "label_status": "illustrative policy labels on synthetic cases"}
    rules = {}
    for cid, r in rules_results.items():
        expected = EXPECTED_ACTIONS.get(cid)
        rules[cid] = {"action": r["final"]["simulated_action"], "status": r["final"]["status"],
                      "expected": expected, "match": r["final"]["simulated_action"] == expected}
    out["arms"]["rules"] = {"cases": rules, "matched": sum(1 for v in rules.values() if v["match"]),
                            "eligible": len(rules)}
    for arm in ("no_jev", "with_jev"):
        cases, matched, eligible, attempted = {}, 0, 0, 0
        for cid, run_ids in exp["arms"][arm].items():
            runs = [runs_by_id[r] for r in run_ids]
            s = summarize_runs(runs)
            expected = EXPECTED_ACTIONS.get(cid)
            # Eligible = finished without provider failure. An INCOMPLETE/REVIEW outcome is a legitimate
            # result for the missing-tool case, but a provider outage never counts as a match.
            finished = [r for r in runs if r["state"] == "completed" and r.get("final")]
            m = sum(1 for r in finished if r["final"]["simulated_action"] == expected)
            cases[cid] = {"summary": s, "expected": expected, "matched_runs": m, "eligible_runs": len(finished),
                          "failures": s["failures"]}
            matched += m
            eligible += len(finished)
            attempted += s["attempted_runs"]
        out["arms"][arm] = {"cases": cases, "matched_runs": matched, "eligible_runs": eligible,
                            "attempted_runs": attempted}
    out["note"] = ("Same cases, tool budget, prompt and policy in every arm; only the stated component "
                   "differs. Five synthetic cases do not establish that Jev improves anything.")
    return out
