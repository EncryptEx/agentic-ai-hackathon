"""G-Eval integration tests. The stub judge is a test double that drives the real DeepEval
GEval code path; it never produces scores shown to users."""

import os
import unittest

from evidencetrail import agent, evaluator
from evidencetrail.eval_fixtures import EXPECTED_ACTIONS
from evidencetrail.scenarios import get_case
from tests.test_evidencetrail import FakeJev, ScriptedModel, finisher, full_plan

try:
    from deepeval.models import DeepEvalBaseLLM
    HAVE_DEEPEVAL = True
except ImportError:  # pragma: no cover
    HAVE_DEEPEVAL = False


def _run(case_id="case-manipulated"):
    case = get_case(case_id)
    model = ScriptedModel(full_plan(case), finisher("CONTEXT_CHECK"))
    return case, agent.investigate(case, model, FakeJev(), "run-geval")


if HAVE_DEEPEVAL:
    class StubJudge(DeepEvalBaseLLM):
        def __init__(self, fail=False):
            self.prompts, self.fail = [], fail
            super().__init__(model="stub-judge")

        def load_model(self):
            return self

        def get_model_name(self):
            return "stub-judge"

        def generate(self, prompt, schema=None, *a, **k):
            self.prompts.append(prompt)
            if self.fail:
                raise RuntimeError("judge exploded")
            if schema is None:
                return "ok"
            values = {}
            for name, field in schema.model_fields.items():
                if "score" in name:
                    values[name] = 8
                elif field.annotation is list or "steps" in name:
                    values[name] = []
                else:
                    values[name] = "stub reason"
            return schema(**values)

        async def a_generate(self, prompt, schema=None, *a, **k):
            return self.generate(prompt, schema)

        def metadata(self):
            return {"judge_requested_model": "stub-judge"}


@unittest.skipUnless(HAVE_DEEPEVAL, "deepeval not installed")
class GEvalIntegration(unittest.TestCase):
    def test_three_official_geval_metrics_are_scored_and_normalized(self):
        case, run = _run()
        out = evaluator.evaluate(run, case, judge_factory=StubJudge)
        self.assertEqual(set(out["geval"]), {"evidence_grounding", "explanation_completeness",
                                             "investigation_relevance"})
        for m in out["geval"].values():
            self.assertEqual(m["status"], "scored", m)
            self.assertTrue(0.0 <= m["score"] <= 1.0)
            self.assertTrue(m["evaluation_steps"])
        self.assertIn("deepeval_version", out["judge"])
        self.assertEqual(out["judge"]["judge_requested_model"], "stub-judge")

    def test_expected_action_label_never_reaches_the_judge(self):
        case, run = _run()
        judge = StubJudge()
        evaluator.evaluate(run, case, judge_factory=lambda: judge)
        blob = "\n".join(judge.prompts)
        self.assertTrue(judge.prompts)
        self.assertNotIn("expected_action", blob)
        self.assertNotIn(case["name"], blob)
        self.assertNotIn(case["case_id"], blob)
        self.assertNotIn("policy label", blob.lower())

    def test_judge_inputs_carry_evidence_with_availability_order(self):
        case, run = _run()
        ctx = "\n".join(evaluator.build_inputs(run, case)["context"])
        self.assertIn("[EV-001] (available from trace step", ctx)
        self.assertIn("ORDERED TRACE:", ctx)

    def test_judge_failure_is_per_metric_error_not_a_fabricated_score(self):
        case, run = _run()
        out = evaluator.evaluate(run, case, judge_factory=lambda: StubJudge(fail=True))
        for m in out["geval"].values():
            self.assertEqual(m["status"], "error")
            self.assertIsNone(m["score"])
        self.assertIn("deterministic", out)

    def test_geval_uses_steps_not_criteria(self):
        import inspect
        src = inspect.getsource(evaluator.evaluate)
        self.assertIn("evaluation_steps=", src)
        self.assertNotIn("criteria=", src)

    def test_deterministic_checks_use_labels_separately(self):
        case, run = _run()
        out = evaluator.evaluate(run, case, judge_factory=StubJudge)
        self.assertEqual(out["deterministic"]["expected_action"], EXPECTED_ACTIONS["case-manipulated"])
        self.assertTrue(out["deterministic"]["policy_label_match"])


class GEvalUnavailable(unittest.TestCase):
    def test_missing_credentials_keep_slots_visible_as_unavailable(self):
        case, run = _run()
        saved = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
        try:
            out = evaluator.evaluate(run, case)  # default judge path, no key
        finally:
            for k, v in saved.items():
                if v:
                    os.environ[k] = v
        self.assertEqual(len(out["geval"]), 3)
        for m in out["geval"].values():
            self.assertEqual(m["status"], "unavailable")
            self.assertIsNone(m["score"])
            self.assertIn("GEMINI_API_KEY", m["reason"])

    def test_run_without_final_decision_is_not_evaluated(self):
        case, run = _run()
        run["final"] = None
        out = evaluator.evaluate(run, case)
        self.assertTrue(all(m["status"] == "unavailable" for m in out["geval"].values()))


if __name__ == "__main__":
    unittest.main()
