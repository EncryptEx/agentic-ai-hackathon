"""Explanation-quality evaluation with the official DeepEval GEval metric.

G-Eval runs after the decision and sits outside the decision path. If DeepEval or the
judge is unavailable, each metric slot stays visible as 'unavailable' with the reason;
no score is ever invented and no generic rubric prompt is passed off as G-Eval.
"""

import json
import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # local evaluation only

from .config import RUBRIC_VERSION
from .jev import ProviderUnavailable
from .metrics import deterministic_checks

METRIC_DEFS = {
    "evidence_grounding": {
        "label": "Evidence grounding",
        "steps": [
            "Identify each material claim in the final explanation (actual output).",
            "For each claim, compare it with the payload of every evidence record it cites in the context.",
            "Penalize claims that are contradicted by, or not supported by, the cited evidence payloads.",
            "Penalize claims that rely on evidence that only became available after the step where the "
            "claim would have been made, or that cite evidence IDs absent from the context.",
            "Do not reward fluent wording; score only how well claims match recorded evidence.",
        ],
    },
    "explanation_completeness": {
        "label": "Explanation completeness",
        "steps": [
            "Identify the decisive policy facts in the evidence context (device, amount range, "
            "recipient novelty, recipient velocity/age, network links, missing or failed checks).",
            "Check whether the final explanation covers those decisive facts.",
            "Check whether the explanation states material remaining uncertainty and missing evidence.",
            "Penalize any claim that authentication or a known device proves the payer's intent or "
            "freedom from manipulation, and any claim that a graph link proves criminality.",
        ],
    },
    "investigation_relevance": {
        "label": "Investigation relevance",
        "steps": [
            "Read the ordered investigation trace in the context.",
            "For each tool call, decide whether the evidence available at that point supports a reason "
            "for making it.",
            "Penalize redundant, irrelevant or unsupported tool calls.",
            "Assess whether stopping or continuing was justified by the evidence available at the time, "
            "including whether missing evidence was treated as missing rather than reassuring.",
        ],
    },
}


def evidence_context(run):
    """Evidence payloads with the trace step at which each became available."""
    available_at = {}
    for e in run["events"]:
        for eid in e.get("output_evidence_ids") or []:
            available_at[eid] = e["sequence"]
    return [f"[{ev['evidence_id']}] (available from trace step {available_at.get(ev['evidence_id'], '?')}) "
            f"type={ev['type']} source={ev['source']} payload={json.dumps(ev['payload'], sort_keys=True)}"
            for ev in run["evidence"]]


def trace_context(run):
    lines = []
    for e in run["events"]:
        if e["event_type"] in ("tool_call", "tool_error", "final_decision", "run_failed"):
            lines.append(f"step {e['sequence']}: {e['event_type']} tool={e['tool_name']} "
                         f"args={json.dumps(e['validated_arguments'], sort_keys=True)} "
                         f"in={e['input_evidence_ids']} out={e['output_evidence_ids']} "
                         f"reason={e['reason_code']}")
    return lines


def build_inputs(run, case):
    """Judge inputs. The expected action is deliberately never supplied: no metric assesses it."""
    final = run["final"]
    claims = "\n".join(f"- {c['text']} (cites: {', '.join(c['supporting_evidence_ids']) or 'none'})"
                       for c in final["claims"]) or "- (no claims submitted)"
    actual = (f"Decision: {final['simulated_action']} (status {final['status']}), rule {final['rule']}.\n"
              f"Policy explanation: {final['explanation']}\nClaims:\n{claims}\n"
              f"Remaining uncertainty: "
              f"{(final.get('agent_recommendation') or {}).get('remaining_uncertainty') or 'not stated'}")
    return {
        "input": json.dumps({"transaction": case["transaction"]}, sort_keys=True),
        "actual_output": actual,
        "context": ["EVIDENCE:"] + evidence_context(run) + ["ORDERED TRACE:"] + trace_context(run),
    }


def evaluate(run, case, judge_factory=None):
    """Return the evaluation block for a run: deterministic checks plus G-Eval slots."""
    result = {"state": "completed", "rubric_version": RUBRIC_VERSION,
              "deterministic": deterministic_checks(run), "geval": {}, "judge": None,
              "judge_note": "Model-based explanation assessment, not independent ground truth."}
    if not run.get("final"):
        reason = "run has no final decision to evaluate"
        result["geval"] = {k: _unavailable(d["label"], reason) for k, d in METRIC_DEFS.items()}
        return result
    try:
        from deepeval import __version__ as deepeval_version
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, SingleTurnParams
    except ImportError:
        result["geval"] = {k: _unavailable(d["label"], "deepeval is not installed")
                           for k, d in METRIC_DEFS.items()}
        return result
    try:
        judge = (judge_factory or _default_judge)()
    except ProviderUnavailable as e:
        result["geval"] = {k: _unavailable(d["label"], str(e)) for k, d in METRIC_DEFS.items()}
        return result

    result["judge"] = {"deepeval_version": deepeval_version}
    inputs = build_inputs(run, case)
    test_case = LLMTestCase(input=inputs["input"], actual_output=inputs["actual_output"],
                            context=inputs["context"])
    params = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.CONTEXT]
    for key, d in METRIC_DEFS.items():
        try:
            metric = GEval(name=d["label"], evaluation_steps=d["steps"], evaluation_params=params,
                           model=judge, async_mode=False, threshold=0.5)
            metric.measure(test_case)
            result["geval"][key] = {"label": d["label"], "status": "scored", "score": metric.score,
                                    "reason": metric.reason, "threshold": metric.threshold,
                                    "passed": metric.is_successful(), "evaluation_steps": d["steps"]}
        except Exception as e:  # one failing metric must not hide the others
            result["geval"][key] = _unavailable(d["label"], f"judge error: {type(e).__name__}: {e}",
                                                status="error")
    result["judge"].update(judge.metadata() if hasattr(judge, "metadata") else {})
    return result


def _unavailable(label, reason, status="unavailable"):
    return {"label": label, "status": status, "score": None, "reason": reason}


def _default_judge():
    from .gemini import GeminiClient
    if not GeminiClient().available():
        raise ProviderUnavailable("GEMINI_API_KEY is not configured, so no G-Eval judge is available")
    from .geval_judge import GeminiJudge
    return GeminiJudge()
