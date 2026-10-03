"""Impact statistics: pure arithmetic over recorded rows. No provider is called."""

import unittest

import _no_live_keys  # noqa: F401

from evidencetrail import impact

A = dict(impact.DEFAULT_ASSUMPTIONS, analyst_minutes_per_alert=30.0, analyst_usd_per_hour=60.0,
         gemini_usd_per_million_input_tokens=1.0, gemini_usd_per_million_output_tokens=2.0, jev_usd_per_call=0.01)


def row(arm, case, truth, flagged, inp=0, out=0, think=0, jev=0, sources=(), geval=None, done=True, amount=100.0):
    return {"arm": arm, "case_id": case, "completed": done, "flagged_by_system": flagged if done else None,
            "action": "REVIEW" if flagged else "ALLOW", "truth_flagged": truth, "amount_usd": amount,
            "alert_sources": list(sources), "jev_calls": jev, "elapsed_ms": 2000, "geval": geval or {},
            "tokens": {"input": inp, "output": out, "thinking": think, "turns": 1, "turns_without_usage": 0}}


class Stats(unittest.TestCase):
    def test_wilson_interval_is_wide_for_small_samples_and_none_for_empty(self):
        self.assertIsNone(impact.wilson(0, 0))
        lo, hi = impact.wilson(5, 10)
        self.assertLess(lo, 0.25)
        self.assertGreater(hi, 0.75)
        self.assertEqual(impact.rate(0, 0)["rate"], None)

    def test_confusion_counts_and_missed_value(self):
        rows = [row("a", "1", True, True), row("a", "2", True, False, amount=500.0),
                row("a", "3", False, True), row("a", "4", False, False), row("a", "5", True, None, done=False)]
        c = impact.confusion(rows)
        self.assertEqual((c["tp"], c["fn"], c["fp"], c["tn"], c["completed"], c["attempted"]), (1, 1, 1, 1, 4, 5))
        self.assertEqual(c["missed_value_usd"], 500.0)
        self.assertEqual(c["recall"]["rate"], 0.5)

    def test_paired_comparison_counts_each_direction(self):
        a = [row("a", "1", True, False), row("a", "2", True, True), row("a", "3", False, True)]
        b = [row("b", "1", True, True), row("b", "2", True, True), row("b", "3", False, True)]
        p = impact.paired(a, b)
        self.assertEqual((p["only_b_correct"], p["only_a_correct"], p["both_correct"], p["both_wrong"]), (1, 0, 1, 1))

    def test_costs_use_the_stated_assumptions(self):
        rows = [row("a", "1", True, True, inp=1_000_000, out=500_000, think=500_000, jev=3),
                row("a", "2", False, True)]
        cost = impact.llm_cost(rows, A)
        self.assertEqual(cost["usd"], round(1.0 + 2.0 + 0.03, 4))
        analyst = impact.analyst_cost(rows, A)
        self.assertEqual((analyst["alerts_reviewed"], analyst["wasted_reviews"], analyst["usd"]), (2, 1, 60.0))

    def test_summary_nets_savings_against_the_rules_baseline(self):
        rows = []
        for i in range(4):  # rules flag everything; both agent arms flag only the truly flagged cases
            truth = i < 2
            rows.append(row("rules", str(i), truth, True))
            rows.append(row("agents_no_jev", str(i), truth, truth, inp=1000))
            rows.append(row("agents_jev", str(i), truth, truth, inp=2000, jev=1, sources=["policy"] if truth else []))
        s = impact.summarize(rows, A)
        self.assertEqual(s["savings_vs_rules"]["agents_jev"]["wasted_reviews_avoided_vs_rules"], 2)
        self.assertEqual(s["savings_vs_rules"]["agents_jev"]["review_usd_saved_vs_rules"], 60.0)
        self.assertEqual(s["jev_effect"]["extra_tokens"]["input"], 4000)
        self.assertEqual(s["jev_effect"]["alerts"]["policy_only"]["detected"]["k"], 2)
        self.assertEqual(s["jev_effect"]["alerts"]["policy_only"]["false_alerts"]["k"], 0)

    def test_geval_gate_reports_how_often_wrong_and_right_decisions_are_held(self):
        fail = {"grounding": {"score": 0.2, "passed": False}}
        ok = {"grounding": {"score": 0.9, "passed": True}}
        rows = [row("agents_jev", "1", True, False, geval=fail), row("agents_jev", "2", True, True, geval=ok),
                row("agents_jev", "3", False, False, geval=fail), row("agents_jev", "4", False, False, geval=ok)]
        g = impact.geval_gate(rows)
        self.assertEqual((g["wrong_held_by_gate"]["k"], g["wrong_held_by_gate"]["n"]), (1, 1))
        self.assertEqual((g["right_held_by_gate"]["k"], g["right_held_by_gate"]["n"]), (1, 3))

    def test_usage_tokens_counts_missing_usage_instead_of_guessing(self):
        events = [{"event_type": "model_turn", "usage_if_available": {"total_input_tokens": 10, "total_output_tokens": 2,
                                                                        "total_thought_tokens": 3}},
                  {"event_type": "model_turn", "usage_if_available": None}, {"event_type": "tool_call"}]
        t = impact.usage_tokens(events)
        self.assertEqual((t["input"], t["output"], t["thinking"], t["turns"], t["turns_without_usage"]), (10, 2, 3, 2, 1))

    def test_context_bench_summary_pairs_baseline_and_reduced_runs(self):
        def res(variant, prompt, ids):
            return {"variant": variant, "data": {"customer": "C1", "prompt_tokens": prompt, "output_tokens": 5, "calls": 4,
                                                 "seconds": 1.0, "cited_ids": ids}}
        s = impact.summarize_context_bench([res("base", 1000, ["TXN-1", "TXN-2"]), res("new", 600, ["TXN-1"])])
        self.assertEqual(s["total_prompt_change"], -0.4)
        self.assertEqual(s["customers"]["C1"]["ids_in_common"], 1)


if __name__ == "__main__":
    unittest.main()
