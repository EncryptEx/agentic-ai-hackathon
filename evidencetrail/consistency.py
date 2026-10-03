"""Decision-consistency report.

A recorded, versioned check that the investigation outcome is stable, run once for a demo and
periodically afterwards (for example monthly, if the company decides to) rather than from the UI:

    python -m evidencetrail.consistency                 # repeats + fixed evidence + evidence-change checks
    python -m evidencetrail.consistency --ablation      # also compare rules / team without Jev / team with Jev

It runs the real agent team and Jev on the hand-built scenarios, writes a timestamped JSON report to
data/consistency/ (override with EVIDENCETRAIL_REPORT_DIR) and exits non-zero when anything varied or
failed, so a scheduler can alert on it. Consistency is not correctness: repeated runs can agree and still
be wrong, and five synthetic cases establish nothing about fraud precision, recall or calibration.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from .canon import now_utc
from .config import (GEMINI_MODEL, JEV_MODEL, JEV_SPEC_VERSION, POLICY_VERSION, SCENARIO_VERSION,
                     TEAM_PROMPT_VERSION)
from .eval_fixtures import EXPECTED_ACTIONS
from .provenance import code_commit
from .scenarios import SCENARIOS

DEFAULT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "consistency"))
_ID = re.compile(r"^consistency-\d{8}-\d{6}$")
SENSITIVITY_CHECKS = (
    ("case-manipulated", "Network links removed",
     {"remove_network_links": True}),
    ("case-manipulated", "Network links removed and recipient made ordinary (400 days old, 2 incoming transfers)",
     {"remove_network_links": True, "recipient": {"account_age_days": 400, "incoming_transfers_last_90_min": 2}}),
)
INTERPRETATION = (
    "Consistency is not correctness. Repeated runs can agree and still be wrong, five synthetic cases establish "
    "nothing about fraud precision, recall or calibration, and the model-based explanation scores are not ground "
    "truth. Counts are raw; no percentage is claimed.")


def report_dir():
    return os.environ.get("EVIDENCETRAIL_REPORT_DIR") or DEFAULT_DIR


# ------------------------------------------------------------------ storage
def save_report(report):
    os.makedirs(report_dir(), exist_ok=True)
    path = os.path.join(report_dir(), report["report_id"] + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    return path


def load_report(report_id):
    if not isinstance(report_id, str) or not _ID.match(report_id):
        return None
    try:
        with open(os.path.join(report_dir(), report_id + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def list_reports():
    """Report metadata, newest first. Unreadable files are skipped, never fatal."""
    try:
        names = [n[:-5] for n in os.listdir(report_dir()) if n.endswith(".json") and _ID.match(n[:-5])]
    except OSError:
        return []
    out = []
    for rid in sorted(names, reverse=True):
        rep = load_report(rid)
        if rep:
            out.append({"report_id": rid, "generated_at": rep.get("generated_at"), "overall": rep.get("overall"),
                        "code": (rep.get("configuration") or {}).get("code")})
    return out


def latest_report():
    metas = list_reports()
    return load_report(metas[0]["report_id"]) if metas else None


# ------------------------------------------------------------------ building the report
def _outcomes(manager, exp):
    """(action, status) of every run that finished without a provider failure, plus the failed runs."""
    finished, failed = [], []
    for rid in exp["run_ids"]:
        run = manager.get(rid)
        final = run.get("final") or {}
        if run["state"] == "completed" and final:
            finished.append((final["simulated_action"], final["status"]))
        else:
            failed.append({"run_id": rid, "reason": run.get("failure") or run.get("error")})
    return finished, failed


def _tally(outcomes):
    counts = {}
    for action, status in outcomes:
        key = action + (" (incomplete)" if status == "INCOMPLETE" else "")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _jev_summary(per_question):
    out, unanimous = {}, True
    for q, v in per_question.items():
        if "counts" in v:
            out[q] = {"counts": v["counts"], "agreement": v["agreement"]}
            unanimous &= v["modal_count"] == v["successful"]
        else:
            out[q] = {"min": v.get("min"), "max": v.get("max"), "mean": v.get("mean")}
    return out, unanimous


def _models_seen(manager, exp):
    agent, jev = set(), set()
    for rid in exp["run_ids"]:
        run = manager.get(rid)
        for e in run.get("events", []):
            if e["event_type"] == "model_turn" and e.get("returned_model_version"):
                agent.add(e["returned_model_version"])
        for ev in run.get("evidence", []):
            if ev["type"] == "jev_assessment" and ev["payload"].get("model"):
                jev.add(ev["payload"]["model"])
    return agent, jev


def run_report(manager, repetitions=5, counterfactual_repetitions=3, include_ablation=False,
               ablation_repetitions=2, scenarios=None, log=lambda message: None, timeout_s=3600, poll_s=3.0):
    """Run the battery and return the report dict (not yet saved). Uses the real providers behind `manager`."""
    case_ids = list(scenarios or SCENARIOS)
    started = time.monotonic()
    repeat = {c: manager.start_repeat(c, "end_to_end", repetitions) for c in case_ids}
    fixed = {c: manager.start_repeat(c, "fixed_evidence", repetitions) for c in case_ids}
    checks = [(c, label, patch, manager.start_counterfactual(c, patch, counterfactual_repetitions))
              for c, label, patch in SENSITIVITY_CHECKS if c in case_ids]
    ablation = manager.start_ablation(case_ids, ablation_repetitions) if include_ablation else None

    pending = {**{("repeat", c): e for c, e in repeat.items()}, **{("fixed", c): e for c, e in fixed.items()},
               **{("check", i): e[3] for i, e in enumerate(checks)}, **({("ablation", 0): ablation} if ablation else {})}
    done_exps, last = {}, -1
    while pending:
        for key, exp_id in list(pending.items()):
            exp = manager.get_experiment(exp_id)
            if exp["state"] in ("completed", "failed"):
                done_exps[key] = exp
                del pending[key]
        if len(done_exps) != last:
            last = len(done_exps)
            log(f"  {last}/{last + len(pending)} experiments finished ({time.monotonic() - started:.0f}s)")
        if pending:
            if time.monotonic() - started > timeout_s:
                raise TimeoutError("consistency report timed out")
            time.sleep(poll_s)

    entries, agent_models, jev_models, total_failed = [], set(), set(), 0
    for cid in case_ids:
        rexp, fexp = done_exps[("repeat", cid)], done_exps[("fixed", cid)]
        outcomes, failed = _outcomes(manager, rexp)
        a, j = _models_seen(manager, rexp)
        agent_models |= a
        jev_models |= j
        total_failed += len(failed)
        counts = _tally(outcomes)
        modal = max(counts, key=counts.get) if counts else None
        agree = len(counts) == 1 and not failed
        res = fexp.get("result")
        fixed_entry, fixed_ok = None, False
        if res:
            d = res["decision"]
            rows = d["runs"]
            ok_rows = [r for r in rows if r["status"] != "ERROR"]
            f_counts = _tally([(r["action"], r["status"]) for r in ok_rows])
            jsum, jev_unanimous = _jev_summary(res["jev"]["per_question"])
            errors = len(rows) - len(ok_rows) + (res["jev"]["attempted"] - res["jev"]["successful"])
            fixed_ok = (len(f_counts) == 1 and len(ok_rows) == len(rows)
                        and res["jev"]["successful"] == res["jev"]["attempted"] and jev_unanimous)
            fixed_entry = {"attempted": d["attempted"], "finished": len(ok_rows), "outcome_counts": f_counts,
                           "agent_actions": [r.get("agent_action") for r in rows],
                           "jev_attempted": res["jev"]["attempted"], "jev_successful": res["jev"]["successful"],
                           "jev": jsum, "all_agree": fixed_ok, "errors": errors, "bundle_hash": res["bundle"]["bundle_hash"]}
            total_failed += errors
        elif fexp["state"] == "failed":
            total_failed += 1
            fixed_entry = {"all_agree": False, "errors": 1, "error": fexp.get("error")}
        summary = rexp["summary"]
        entries.append({
            "case_id": cid, "name": SCENARIOS[cid]["name"], "expected_action": EXPECTED_ACTIONS.get(cid),
            "repeat": {"attempted": repetitions, "finished": len(outcomes), "failed": failed, "outcome_counts": counts,
                       "modal_outcome": modal, "all_runs_agree": agree,
                       "specialist_paths": summary["specialist_sequences"], "tool_paths": summary["tool_sequences"],
                       "elapsed_ms": [x for x in summary["elapsed_ms"] if x is not None]},
            "fixed_evidence": fixed_entry,
            "matches_policy_label": bool(modal) and modal.split(" (")[0] == EXPECTED_ACTIONS.get(cid),
            "consistent": bool(agree and fixed_ok),
        })

    base = next((e for e in entries if e["case_id"] == "case-manipulated"), None)
    sensitivity = []
    for i, (cid, label, patch, _) in enumerate(checks):
        exp = done_exps[("check", i)]
        outcomes, failed = _outcomes(manager, exp)
        total_failed += len(failed)
        counts = _tally(outcomes)
        sensitivity.append({"case_id": cid, "change": label, "patch": patch, "repetitions": counterfactual_repetitions,
                            "outcome_counts": counts, "failed": failed,
                            "baseline_outcome": base and base["repeat"]["modal_outcome"],
                            "action_changed": bool(base) and set(counts) != {base["repeat"]["modal_outcome"]},
                            "note": "Shows sensitivity under this evidence change; it does not prove causal correctness "
                                    "or that every risk reduction should change the action."})

    report = {
        "report_id": "consistency-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "kind": "decision_consistency", "generated_at": now_utc(), "duration_s": round(time.monotonic() - started),
        "configuration": {
            "repetitions": repetitions, "counterfactual_repetitions": counterfactual_repetitions,
            "scenarios": case_ids, "run_mode": getattr(manager, "_run_mode", "live"),
            "agent_model_requested": GEMINI_MODEL, "agent_models_returned": sorted(agent_models),
            "jev_model_requested": JEV_MODEL, "jev_models_returned": sorted(jev_models),
            "versions": {"team_prompt": TEAM_PROMPT_VERSION, "policy": POLICY_VERSION, "jev_spec": JEV_SPEC_VERSION,
                         "scenarios": SCENARIO_VERSION},
            "code": code_commit()},
        "scenarios": entries, "sensitivity": sensitivity,
        "overall": {"scenarios": len(entries), "fully_consistent": sum(e["consistent"] for e in entries),
                    "match_policy_labels": sum(e["matches_policy_label"] for e in entries), "failed_runs": total_failed},
        "interpretation": INTERPRETATION,
    }
    if ablation:
        report["ablation"] = done_exps[("ablation", 0)]["summary"]
    return report


def verdict_exit_code(report):
    o = report["overall"]
    return 0 if o["fully_consistent"] == o["scenarios"] and o["failed_runs"] == 0 else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description="EvidenceTrail decision-consistency report (live providers)")
    parser.add_argument("--repetitions", type=int, default=5, help="fresh runs per scenario (default 5)")
    parser.add_argument("--ablation", action="store_true", help="also compare rules / team without Jev / team with Jev")
    parser.add_argument("--scenario", action="append", choices=list(SCENARIOS), help="limit to scenarios (repeatable)")
    args = parser.parse_args(argv)
    if not 1 <= args.repetitions <= 20:
        parser.error("--repetitions must be between 1 and 20")
    from .runs import RunManager
    print(f"Running the consistency battery ({args.repetitions} runs per scenario) against live providers...", flush=True)
    report = run_report(RunManager(), repetitions=args.repetitions, include_ablation=args.ablation,
                        scenarios=args.scenario, log=lambda m: print(m, flush=True))
    path = save_report(report)
    o = report["overall"]
    print(f"\nReport saved: {path}")
    print(f"{o['fully_consistent']}/{o['scenarios']} scenarios fully consistent, "
          f"{o['match_policy_labels']}/{o['scenarios']} match the illustrative policy labels, {o['failed_runs']} failed runs")
    for e in report["scenarios"]:
        print(f"  {e['case_id']:18} runs={e['repeat']['outcome_counts']} fixed={'agree' if (e['fixed_evidence'] or {}).get('all_agree') else 'varied'}"
              f" -> {'consistent' if e['consistent'] else 'VARIED'}")
    code = verdict_exit_code(report)
    sys.exit(code)


if __name__ == "__main__":
    main()
