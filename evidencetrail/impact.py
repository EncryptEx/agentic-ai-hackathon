"""Impact study: what do Jev, G-Eval and context reduction add, and what does it cost or save?

    python -m evidencetrail.impact --each 24 --evaluate        # live: spends Gemini and Jev quota

Arms, all on the same labelled seed transactions (the generator's answer key is used by this evaluator only):
  rules          policy v1 over all evidence, no model, no Jev        (free baseline)
  agents_no_jev  the agent team without Jev
  agents_jev     the full system (agent team consulting Jev, plus Jev alert triage)

Everything counted here is measured. Money comes from two clearly labelled inputs: provider prices and analyst
cost, both ASSUMPTIONS in DEFAULT_ASSUMPTIONS that the reader must replace with their own. Counts come from a
sample that is enriched with attacks, so rates describe this sample, not a real portfolio.
"""

import json
import math
import os
import time

DEFAULT_ASSUMPTIONS = {
    "gemini_usd_per_million_input_tokens": 0.30,     # ASSUMPTION: replace with your Gemini price
    "gemini_usd_per_million_output_tokens": 2.50,    # ASSUMPTION: thinking tokens are billed as output
    "jev_usd_per_call": 0.0,                          # ASSUMPTION: unknown, set it if Jev is priced per call
    "analyst_minutes_per_alert": 25.0,                # ASSUMPTION: time to review one flagged transfer by hand
    "analyst_usd_per_hour": 45.0,                     # ASSUMPTION: fully loaded analyst cost
}
ARMS = ("rules", "agents_no_jev", "agents_jev")


def assumptions():
    merged = dict(DEFAULT_ASSUMPTIONS)
    path = os.environ.get("EVIDENCETRAIL_ASSUMPTIONS")
    if path and os.path.exists(path):
        merged.update(json.load(open(path, encoding="utf-8")))
    return merged


# ------------------------------------------------------------------ statistics helpers
def wilson(k, n, z=1.96):
    """95% Wilson interval for a proportion; None when there is nothing to estimate."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def rate(k, n):
    return {"k": k, "n": n, "rate": None if n == 0 else round(k / n, 3), "ci95": wilson(k, n)}


def usage_tokens(events):
    """Sum the usage the provider reported on model turns. Missing usage is counted, never guessed."""
    t = {"input": 0, "output": 0, "thinking": 0, "turns": 0, "turns_without_usage": 0}
    for e in events or []:
        if e.get("event_type") != "model_turn":
            continue
        t["turns"] += 1
        u = e.get("usage_if_available")
        if not isinstance(u, dict):
            t["turns_without_usage"] += 1
            continue
        t["input"] += int(u.get("total_input_tokens") or 0)
        t["output"] += int(u.get("total_output_tokens") or 0)
        t["thinking"] += int(u.get("total_thought_tokens") or 0)
    return t


def row_from_run(run, arm, truth, amount=None):
    """One comparable row from a finished run (or from the rules arm)."""
    final = run.get("final") or {}
    done = run.get("state") == "completed" and bool(final)
    alert = run.get("alert") or {}
    events = run.get("events") or []
    ev = run.get("evaluation") or {}
    geval = {k: {"score": v.get("score"), "passed": v.get("passed")}
             for k, v in (ev.get("geval") or {}).items() if v.get("status") == "scored"}
    return {"arm": arm, "case_id": run["case_id"], "completed": done,
            "flagged_by_system": (final.get("simulated_action") != "ALLOW") if done else None,
            "action": final.get("simulated_action") if done else None,
            "truth_flagged": truth, "amount_usd": amount,
            "alert_sources": alert.get("sources") or [], "tokens": usage_tokens(events),
            "jev_calls": sum(1 for e in events if e.get("provider") == "jev"),   # assessments and alert triage
            "elapsed_ms": run.get("elapsed_ms"), "geval": geval}


# ------------------------------------------------------------------ summaries
def confusion(rows):
    ok = [r for r in rows if r["completed"]]
    tp = sum(1 for r in ok if r["truth_flagged"] and r["flagged_by_system"])
    fn = sum(1 for r in ok if r["truth_flagged"] and not r["flagged_by_system"])
    fp = sum(1 for r in ok if not r["truth_flagged"] and r["flagged_by_system"])
    tn = sum(1 for r in ok if not r["truth_flagged"] and not r["flagged_by_system"])
    return {"attempted": len(rows), "completed": len(ok), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "recall": rate(tp, tp + fn), "false_positive_rate": rate(fp, fp + tn),
            "precision": rate(tp, tp + fp),
            "missed_value_usd": round(sum(r["amount_usd"] or 0 for r in ok
                                          if r["truth_flagged"] and not r["flagged_by_system"]), 2)}


def paired(a_rows, b_rows):
    """How often B (with the component) is right where A is wrong, and the reverse. Same cases only."""
    a = {r["case_id"]: r for r in a_rows if r["completed"]}
    b = {r["case_id"]: r for r in b_rows if r["completed"]}
    wins = losses = both = neither = 0
    for cid in a.keys() & b.keys():
        ra = a[cid]["flagged_by_system"] == a[cid]["truth_flagged"]
        rb = b[cid]["flagged_by_system"] == b[cid]["truth_flagged"]
        wins += (not ra) and rb
        losses += ra and (not rb)
        both += ra and rb
        neither += (not ra) and (not rb)
    return {"cases": len(a.keys() & b.keys()), "only_b_correct": wins, "only_a_correct": losses,
            "both_correct": both, "both_wrong": neither}


def llm_cost(rows, a):
    t = {"input": 0, "output": 0, "thinking": 0}
    for r in rows:
        for k in t:
            t[k] += r["tokens"][k]
    usd = (t["input"] * a["gemini_usd_per_million_input_tokens"]
           + (t["output"] + t["thinking"]) * a["gemini_usd_per_million_output_tokens"]) / 1e6
    usd += sum(r["jev_calls"] for r in rows) * a["jev_usd_per_call"]
    n = max(1, sum(1 for r in rows if r["completed"]))
    return {"tokens": t, "usd": round(usd, 4), "usd_per_case": round(usd / n, 5)}


def analyst_cost(rows, a):
    """Hand review of everything the arm flags. False positives are review time that bought nothing."""
    ok = [r for r in rows if r["completed"]]
    flagged = sum(1 for r in ok if r["flagged_by_system"])
    wasted = sum(1 for r in ok if r["flagged_by_system"] and not r["truth_flagged"])
    per = a["analyst_minutes_per_alert"] / 60 * a["analyst_usd_per_hour"]
    return {"alerts_reviewed": flagged, "wasted_reviews": wasted, "usd": round(flagged * per, 2),
            "wasted_usd": round(wasted * per, 2), "usd_per_review": round(per, 2)}


def geval_gate(rows):
    """Treat a failed G-Eval metric as 'hold for a human'. Does that catch wrong decisions without crying wolf?"""
    scored = [r for r in rows if r["completed"] and r["geval"]]
    def gated(r):
        return any(v["passed"] is False for v in r["geval"].values())
    wrong = [r for r in scored if r["flagged_by_system"] != r["truth_flagged"]]
    right = [r for r in scored if r["flagged_by_system"] == r["truth_flagged"]]
    metrics = {}
    for name in sorted({k for r in scored for k in r["geval"]}):
        vals = [r["geval"][name]["score"] for r in scored if name in r["geval"] and r["geval"][name]["score"] is not None]
        metrics[name] = {"mean": round(sum(vals) / len(vals), 3) if vals else None, "n": len(vals),
                         "pass": rate(sum(1 for r in scored if (r["geval"].get(name) or {}).get("passed")), len(scored))}
    return {"evaluated_runs": len(scored), "wrong_decisions": len(wrong), "right_decisions": len(right),
            "wrong_held_by_gate": rate(sum(gated(r) for r in wrong), len(wrong)),
            "right_held_by_gate": rate(sum(gated(r) for r in right), len(right)), "metrics": metrics,
            "reading": ("A gate is useful only if it holds wrong decisions clearly more often than right ones. "
                        "G-Eval is a model judging explanations, not ground truth.")}


def alert_sources(rows):
    ok = [r for r in rows if r["completed"]]
    out = {}
    for label, pred in (("policy_only", lambda r: "policy" in r["alert_sources"]),
                        ("jev_only", lambda r: "jev" in r["alert_sources"]),
                        ("jev_or_policy", lambda r: bool(r["alert_sources"]))):
        flagged = [r for r in ok if r["truth_flagged"]]
        clean = [r for r in ok if not r["truth_flagged"]]
        out[label] = {"detected": rate(sum(pred(r) for r in flagged), len(flagged)),
                      "false_alerts": rate(sum(pred(r) for r in clean), len(clean))}
    return out


def summarize(rows, a=None):
    a = a or assumptions()
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    arms = {}
    for arm, rs in by_arm.items():
        arms[arm] = {"detection": confusion(rs), "llm_cost": llm_cost(rs, a), "analyst": analyst_cost(rs, a)}
        mean_ms = [r["elapsed_ms"] for r in rs if r["elapsed_ms"]]
        arms[arm]["mean_seconds_per_case"] = round(sum(mean_ms) / len(mean_ms) / 1000, 1) if mean_ms else None
        arms[arm]["net_usd"] = round(arms[arm]["llm_cost"]["usd"] + arms[arm]["analyst"]["usd"], 2)
    base = arms["rules"]["analyst"]
    savings = {}
    for arm in ("agents_no_jev", "agents_jev"):
        savings[arm] = {"wasted_reviews_avoided_vs_rules": base["wasted_reviews"] - arms[arm]["analyst"]["wasted_reviews"],
                        "review_usd_saved_vs_rules": round(base["usd"] - arms[arm]["analyst"]["usd"], 2),
                        "llm_usd_spent": arms[arm]["llm_cost"]["usd"],
                        "net_usd_vs_rules": round(base["usd"] - arms[arm]["analyst"]["usd"] - arms[arm]["llm_cost"]["usd"], 2),
                        "extra_missed_value_usd_vs_rules": round(arms[arm]["detection"]["missed_value_usd"]
                                                                 - arms["rules"]["detection"]["missed_value_usd"], 2)}
    return {
        "assumptions": a, "arms": arms, "savings_vs_rules": savings,
        "jev_effect": {"paired_vs_no_jev": paired(by_arm["agents_no_jev"], by_arm["agents_jev"]),
                       "alerts": alert_sources(by_arm["agents_jev"]),
                       "extra_tokens": {k: arms["agents_jev"]["llm_cost"]["tokens"][k] - arms["agents_no_jev"]["llm_cost"]["tokens"][k]
                                        for k in ("input", "output", "thinking")}},
        "geval_effect": geval_gate(by_arm["agents_jev"]),
        "notes": ["Rates come from a sample enriched with attacks and cover a few dozen transactions; the confidence "
                  "intervals are wide and say so.",
                  "Money uses the ASSUMPTIONS above. Token counts, decisions and missed value are measured.",
                  "The answer key marks every generator-planted transaction, including early ones nothing could know "
                  "yet, so recall below 100% is expected."],
    }


def summarize_context_bench(results):
    """ADK paired runs (baseline code vs context reduction): measured Gemini usage, same customers."""
    out = {}
    by_c = {}
    for r in results:
        by_c.setdefault(r["data"]["customer"], {})[r["variant"]] = r["data"]
    pairs = {c: v for c, v in by_c.items() if "base" in v and "new" in v}
    for c, v in pairs.items():
        b, n = v["base"], v["new"]
        shared = set(b["cited_ids"]) & set(n["cited_ids"])
        out[c] = {"prompt_tokens": [b["prompt_tokens"], n["prompt_tokens"]],
                  "output_tokens": [b["output_tokens"], n["output_tokens"]],
                  "calls": [b["calls"], n["calls"]], "seconds": [b["seconds"], n["seconds"]],
                  "prompt_change": round(n["prompt_tokens"] / b["prompt_tokens"] - 1, 3) if b["prompt_tokens"] else None,
                  "ids_cited": [len(b["cited_ids"]), len(n["cited_ids"])], "ids_in_common": len(shared)}
    tb = sum(v["base"]["prompt_tokens"] for v in pairs.values())
    tn = sum(v["new"]["prompt_tokens"] for v in pairs.values())
    return {"customers": out, "total_prompt_tokens": [tb, tn],
            "total_prompt_change": round(tn / tb - 1, 3) if tb else None,
            "condense_compress_api": "not measured: the account's compress API returned 402 (no credit balance)"}


# ------------------------------------------------------------------ live study
def select_cases(each, seed_value=7):
    import random
    from .seed import CASE_PREFIX, get_seed
    from .seed_labels import ground_truth
    flagged, clean = [], []
    for c in get_seed().candidates():
        tid = c["transaction"]["transaction_id"]
        truth = ground_truth(tid)
        (flagged if truth["flagged"] else clean).append((c["case_id"], truth["flagged"], c["transaction"]["amount"]))
    rnd = random.Random(seed_value)
    rnd.shuffle(flagged)
    rnd.shuffle(clean)
    return flagged[:each] + clean[:each]


def run_study(each=24, evaluate=True, out_dir="data/impact", on_log=print):
    from .alerts import AlertStore
    from .experiments import rules_baseline
    from .runs import RunManager
    from .scenarios import get_case
    mgr = RunManager(alert_store=AlertStore(":memory:"))
    cases = select_cases(each)
    on_log(f"{len(cases)} cases ({sum(1 for c in cases if c[1])} flagged by the answer key)")
    rows, started = [], {}
    for cid, truth, amount in cases:
        res = rules_baseline(get_case(cid))
        rows.append({"arm": "rules", "case_id": cid, "completed": True,
                     "flagged_by_system": res["final"]["simulated_action"] != "ALLOW",
                     "action": res["final"]["simulated_action"], "truth_flagged": truth, "amount_usd": amount,
                     "alert_sources": [], "tokens": {"input": 0, "output": 0, "thinking": 0, "turns": 0,
                                                     "turns_without_usage": 0},
                     "jev_calls": 0, "elapsed_ms": None, "geval": {}})
        started[(cid, "agents_no_jev")] = mgr.start(cid, {"study": "no_jev"}, arm="no_jev", alerts_enabled=False)
        started[(cid, "agents_jev")] = mgr.start(cid, {"study": "jev"}, arm="with_jev", alerts_enabled="triage_only")
    truth_by_case = {c[0]: (c[1], c[2]) for c in cases}
    t0 = time.monotonic()
    while True:
        states = [mgr._runs[r]["state"] for r in started.values()]
        done = sum(s in ("completed", "failed") for s in states)
        on_log(f"runs finished {done}/{len(states)} after {int(time.monotonic() - t0)}s")
        if done == len(states):
            break
        time.sleep(30)
    if evaluate:
        for (cid, arm), rid in started.items():
            if arm == "agents_jev" and mgr._runs[rid]["state"] == "completed":
                try:
                    mgr.start_evaluation(rid)
                except Exception as e:
                    on_log(f"evaluation not started for {rid}: {type(e).__name__}")
        judged = [r for (c, arm), r in started.items() if arm == "agents_jev" and mgr._runs[r].get("evaluation")]
        while any(mgr._runs[r]["evaluation"].get("state") == "running" for r in judged):
            time.sleep(10)
    for (cid, arm), rid in started.items():
        truth, amount = truth_by_case[cid]
        rows.append(row_from_run(mgr._runs[rid], arm, truth, amount))
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(out_dir, f"impact-{stamp}.json")
    result = {"created": stamp, "cases": len(cases), "rows": rows, "summary": summarize(rows)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    on_log(f"saved {path}")
    return result


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--each", type=int, default=24, help="cases per class (flagged / clean)")
    p.add_argument("--no-evaluate", action="store_true")
    args = p.parse_args()
    run_study(args.each, evaluate=not args.no_evaluate)
