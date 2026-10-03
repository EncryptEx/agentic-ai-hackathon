"""Live provider check:  python -m evidencetrail.live_check [--e2e]

Confirms the wire formats this project guessed from the docs against the real Gemini and Jev APIs,
and optionally runs all five scenarios end to end. It prints PASS / FAIL / SKIP per check and never
prints a key. --e2e spends real quota (several Gemini calls per case plus Jev calls).
"""

import argparse
import sys

from . import alerts, evaluator, team
from .config import gemini_key, jev_key
from .eval_fixtures import EXPECTED_ACTIONS
from .experiments import gather_all
from .gemini import GeminiClient
from .jev import ALERT_QUESTIONS, JEV_QUESTIONS, JevClient, ProviderUnavailable, build_state
from .scenarios import SCENARIOS, get_case
from .tools import TOOL_DECLARATIONS

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def _result(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


def check_keys():
    out = []
    for name, present in (("GEMINI_API_KEY", bool(gemini_key())), ("TYPESAFE_API_KEY", bool(jev_key()))):
        out.append(_result(f"key {name}", PASS if present else FAIL,
                           "set" if present else "missing: add it to .env or the environment"))
    return out


def check_gemini(client):
    if not client.available():
        return [_result("gemini function call", SKIP, "no Gemini key")]
    decl = next(d for d in TOOL_DECLARATIONS if d["name"] == "get_behavior_profile")
    steps = [{"type": "user_input", "content": "Call the get_behavior_profile tool for customer CUST-A101."}]
    results = []
    try:
        turn = client.generate("You are a connectivity test. Use the provided tool when asked.", steps, [decl])
    except ProviderUnavailable as e:
        return [_result("gemini function call", FAIL, str(e))]
    types = sorted({s.get("type", "?") for s in turn.steps})
    call = next((c for c in turn.calls if c["name"] == "get_behavior_profile"), None)
    if call is None:
        return [_result("gemini function call", FAIL, f"no function_call returned; step types seen: {types}; text={turn.text[:80]!r}")]
    args_ok = isinstance(call["arguments"], dict) and call["arguments"].get("customer_id")
    results.append(_result("gemini function call", PASS if args_ok else FAIL,
                           f"model={turn.returned_model_version}; step types={types}; args={call['arguments']}"))
    follow = steps + turn.steps + [{"type": "function_result", "name": call["name"], "call_id": call["id"],
                                    "result": [{"type": "text", "text": '{"typical_amount_max": 2000}'}]}]
    try:
        turn2 = client.generate("You are a connectivity test. Use the provided tool when asked.", follow, [decl])
    except ProviderUnavailable as e:
        results.append(_result("gemini continuation (function_result)", FAIL, str(e)))
        return results
    results.append(_result("gemini continuation (function_result)", PASS,
                           f"step types={sorted({s.get('type', '?') for s in turn2.steps})}"))
    results.append(_result("gemini text extraction", PASS if turn2.text.strip() or turn2.calls else FAIL,
                           f"text={turn2.text[:80]!r}" if turn2.text.strip() else
                           "no text and no call in the continuation; check the text step type name in gemini._extract_text"))
    return results


def _jev_shape(name, client, state, questions, expect):
    try:
        res = client.assess(state, questions=questions)
    except ProviderUnavailable as e:
        return _result(name, FAIL, str(e))
    norm = res["normalized"]
    missing = [q for q in questions if q not in norm]
    if missing:
        return _result(name, FAIL, f"answers missing for {missing}; raw keys={sorted((res['raw'].get('answers') or {}))}")
    problems = expect(norm)
    return _result(name, FAIL if problems else PASS, problems or f"model={res['model']}; normalized={norm}")


def check_jev(client):
    if not client.available():
        return [_result("jev questions", SKIP, "no TypeSafe key")]
    case = get_case("case-manipulated")
    store = gather_all(case)
    state = build_state([e for e in store.all() if e["type"] != "tool_error"])

    def tool_expect(n):
        bad = []
        if n["recipient_risk"] not in JEV_QUESTIONS["recipient_risk"]["criteria"]:
            bad.append(f"recipient_risk={n['recipient_risk']!r} is not one of its options")
        if n["next_step"] not in JEV_QUESTIONS["next_step"]["criteria"]:
            bad.append(f"next_step={n['next_step']!r} is not one of its options")
        if not isinstance(n["manipulation_indicators"], (int, float)):
            bad.append(f"noul answer is {type(n['manipulation_indicators']).__name__}, expected a number")
        return "; ".join(bad)

    def triage_expect(n):
        bad = []
        if n["suspicion"] not in ALERT_QUESTIONS["suspicion"]["criteria"]:
            bad.append(f"suspicion={n['suspicion']!r} is not one of its options")
        if not isinstance(n["severity"], (int, float)):
            bad.append(f"score answer is {type(n['severity']).__name__}, expected a number")
        return "; ".join(bad)

    triage_input = alerts.triage_state(case, store)
    return [_jev_shape("jev choice + noul (agent tool questions)", client, state, JEV_QUESTIONS, tool_expect),
            _jev_shape("jev choice + score (alert triage questions)", client, triage_input, ALERT_QUESTIONS, triage_expect)]


def check_e2e(model, jev):
    if not model.available():
        return [_result("e2e", SKIP, "no Gemini key")]
    out, runs = [], {}
    for cid in SCENARIOS:
        case = get_case(cid)
        try:
            r = team.investigate_team(case, model, jev, f"live-{cid}", run_mode="live", triage=jev.available())
        except Exception as e:  # report, never crash the whole check
            out.append(_result(f"e2e {cid}", FAIL, f"{type(e).__name__}: {e}"))
            continue
        runs[cid] = (case, r)
        final = r["final"] or {}
        expected = EXPECTED_ACTIONS[cid]
        action = final.get("simulated_action")
        status = PASS if (action == expected and not r["failure"]) else FAIL
        alert = r.get("alert")
        out.append(_result(
            f"e2e {cid}", status,
            f"action={action} expected={expected} ({final.get('status')}); tools={r['tool_call_count']} "
            f"consultations={r.get('consultation_count')}; alert={(alert or {}).get('severity') or 'none'}"
            + (f"; failure={r['failure']}" if r["failure"] else "")))
    out += check_geval(runs.get("case-manipulated"))
    return out


def check_geval(entry):
    """Score one real run with the real G-Eval judge (three official GEval metrics)."""
    if entry is None:
        return [_result("g-eval judge", SKIP, "no completed run to evaluate")]
    case, run = entry
    try:
        ev = evaluator.evaluate(run, case)
    except Exception as e:
        return [_result("g-eval judge", FAIL, f"{type(e).__name__}: {e}")]
    metrics = ev["geval"]
    bad = {k: m for k, m in metrics.items() if m["status"] != "scored"}
    if bad:
        return [_result("g-eval judge", FAIL, "; ".join(f"{k}: {m['status']} {m['reason'][:160]}" for k, m in bad.items()))]
    return [_result("g-eval judge", PASS, "; ".join(
        f"{m['label']}={m['score']:.2f}" for m in metrics.values()) + f"; judge={ev['judge'].get('judge_requested_model')}")]


def run_checks(e2e=False, gemini=None, jev=None):
    gemini = gemini or GeminiClient()
    jev = jev or JevClient()
    results = check_keys() + check_gemini(gemini) + check_jev(jev)
    if e2e:
        results += check_e2e(gemini, jev)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Live provider check")
    parser.add_argument("--e2e", action="store_true", help="also run all five scenarios end to end (spends quota)")
    args = parser.parse_args(argv)
    results = run_checks(e2e=args.e2e)
    for r in results:
        print(f"[{r['status']}] {r['name']}" + (f" - {r['detail']}" if r["detail"] else ""))
    failed = [r for r in results if r["status"] == FAIL]
    print(f"\n{len(results) - len(failed)} ok/skipped, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
