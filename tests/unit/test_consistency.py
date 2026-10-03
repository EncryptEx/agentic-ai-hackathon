"""Decision-consistency report: building, storing, read-only API, and failure visibility."""

import json
import os
import tempfile
import unittest

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)

from evidencetrail import api, consistency
from evidencetrail.alerts import AlertStore
from evidencetrail.runs import RunManager
from fakes import FakeJev, FlakyTeam, TeamAndDecider

CASES = ["case-familiar", "case-manipulated", "case-missing-tool"]


def run_report(*args, **kwargs):
    kwargs.setdefault("poll_s", 0.05)  # the real default polls every few seconds
    return consistency.run_report(*args, **kwargs)


def manager(model_factory=TeamAndDecider):
    return RunManager(model_factory=model_factory, jev_factory=FakeJev, alert_store=AlertStore(":memory:"))


class ReportDirMixin:
    def setUp(self):
        self._saved = os.environ.get("EVIDENCETRAIL_REPORT_DIR")
        self.dir = tempfile.mkdtemp()
        os.environ["EVIDENCETRAIL_REPORT_DIR"] = self.dir

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("EVIDENCETRAIL_REPORT_DIR", None)
        else:
            os.environ["EVIDENCETRAIL_REPORT_DIR"] = self._saved


class Building(ReportDirMixin, unittest.TestCase):
    def test_report_covers_repeats_frozen_evidence_and_sensitivity(self):
        r = run_report(manager(), repetitions=3, counterfactual_repetitions=2, scenarios=CASES)
        self.assertEqual([e["case_id"] for e in r["scenarios"]], CASES)
        fam = r["scenarios"][0]
        self.assertEqual(fam["repeat"]["outcome_counts"], {"ALLOW": 3})
        self.assertTrue(fam["repeat"]["all_runs_agree"])
        self.assertEqual(fam["fixed_evidence"]["attempted"], 3)
        self.assertTrue(fam["fixed_evidence"]["all_agree"])
        self.assertEqual(fam["expected_action"], "ALLOW")
        self.assertTrue(fam["matches_policy_label"] and fam["consistent"])
        self.assertEqual(len(r["sensitivity"]), 2)           # both evidence-change checks on the manipulated case
        self.assertEqual({s["repetitions"] for s in r["sensitivity"]}, {2})
        self.assertEqual(r["overall"], {"scenarios": 3, "fully_consistent": 3, "match_policy_labels": 3, "failed_runs": 0})

    def test_a_consistently_incomplete_scenario_counts_as_consistent_and_matching(self):
        r = run_report(manager(), repetitions=3, scenarios=["case-missing-tool"])
        e = r["scenarios"][0]
        self.assertEqual(e["repeat"]["outcome_counts"], {"REVIEW (incomplete)": 3})
        self.assertTrue(e["consistent"] and e["matches_policy_label"])
        self.assertEqual(r["overall"]["failed_runs"], 0)

    def test_evidence_change_checks_show_whether_the_action_follows_the_evidence(self):
        r = run_report(manager(), repetitions=2, counterfactual_repetitions=2, scenarios=["case-manipulated"])
        by_label = {s["change"]: s for s in r["sensitivity"]}
        links_only = by_label["Network links removed"]
        both = next(s for k, s in by_label.items() if "recipient made ordinary" in k)
        self.assertEqual(links_only["baseline_outcome"], "CONTEXT_CHECK")
        self.assertFalse(links_only["action_changed"])        # the young high-velocity recipient alone still triggers the check
        self.assertTrue(both["action_changed"])
        self.assertEqual(both["outcome_counts"], {"ALLOW": 2})
        self.assertIn("does not prove causal correctness", both["note"])

    def test_metadata_records_models_versions_and_code(self):
        r = run_report(manager(), repetitions=2, scenarios=["case-familiar"])
        c = r["configuration"]
        self.assertEqual(c["repetitions"], 2)
        self.assertIn("commit", c["code"])
        self.assertEqual(set(c["versions"]), {"team_prompt", "policy", "jev_spec", "scenarios"})
        self.assertEqual(c["jev_models_returned"], ["jev-fake-1"])
        self.assertEqual(c["agent_models_returned"], ["scripted-team-1"])
        self.assertIn("Consistency is not correctness", r["interpretation"])

    def test_ablation_is_optional_and_included_on_request(self):
        r = run_report(manager(), repetitions=2, scenarios=["case-familiar"], include_ablation=True,
                                   ablation_repetitions=1)
        self.assertEqual(r["ablation"]["arms"]["rules"]["matched"], 1)
        self.assertNotIn("ablation", run_report(manager(), repetitions=1, scenarios=["case-familiar"]))

    def test_provider_failures_are_counted_and_flip_the_verdict(self):
        FlakyTeam._count = 0
        r = run_report(manager(FlakyTeam), repetitions=4, scenarios=["case-familiar"])
        self.assertGreater(r["overall"]["failed_runs"], 0)
        self.assertFalse(r["scenarios"][0]["consistent"])
        self.assertTrue(r["scenarios"][0]["repeat"]["failed"])
        self.assertEqual(consistency.verdict_exit_code(r), 2)

    def test_clean_report_exits_zero(self):
        r = run_report(manager(), repetitions=2, scenarios=["case-familiar"])
        self.assertEqual(consistency.verdict_exit_code(r), 0)

    def test_report_never_contains_credentials(self):
        r = run_report(manager(), repetitions=1, scenarios=["case-familiar"])
        blob = json.dumps(r).lower()
        for needle in ("api_key", "authorization", "bearer", "aiza"):
            self.assertNotIn(needle, blob)


class Storage(ReportDirMixin, unittest.TestCase):
    def _report(self, rid, overall=None):
        return {"report_id": rid, "generated_at": "2026-10-03T12:00:00+00:00", "overall": overall or {"scenarios": 1},
                "configuration": {"code": {"commit": "abc"}}}

    def test_save_load_list_latest(self):
        consistency.save_report(self._report("consistency-20261001-100000"))
        consistency.save_report(self._report("consistency-20261101-100000"))
        self.assertEqual([m["report_id"] for m in consistency.list_reports()],
                         ["consistency-20261101-100000", "consistency-20261001-100000"])
        self.assertEqual(consistency.latest_report()["report_id"], "consistency-20261101-100000")
        self.assertEqual(consistency.load_report("consistency-20261001-100000")["configuration"]["code"]["commit"], "abc")

    def test_ids_are_validated_so_paths_cannot_be_traversed(self):
        for bad in ("../secrets", "consistency-1", "consistency-20261001-100000/../x", None, 5, ""):
            self.assertIsNone(consistency.load_report(bad))

    def test_empty_or_unreadable_state_is_fine(self):
        self.assertEqual(consistency.list_reports(), [])
        self.assertIsNone(consistency.latest_report())
        with open(os.path.join(self.dir, "consistency-20261001-100000.json"), "w") as f:
            f.write("{not json")
        self.assertEqual(consistency.list_reports(), [])

    def test_cli_rejects_out_of_range_repetitions_before_touching_providers(self):
        with self.assertRaises(SystemExit) as ctx:
            consistency.main(["--repetitions", "0"])
        self.assertEqual(ctx.exception.code, 2)


class ReadOnlyApi(ReportDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        api.set_manager(manager())

    def test_endpoints_list_latest_and_fetch_a_report(self):
        status, body = api.handle_get("/api/evidencetrail/consistency")
        self.assertEqual((status, body["reports"], body["latest"]), (200, [], None))
        self.assertEqual(body["run_command"], "python -m evidencetrail.consistency")
        report = run_report(manager(), repetitions=2, scenarios=["case-familiar"])
        consistency.save_report(report)
        status, body = api.handle_get("/api/evidencetrail/consistency")
        self.assertEqual(body["latest"]["report_id"], report["report_id"])
        self.assertEqual(api.handle_get(f"/api/evidencetrail/consistency/{report['report_id']}")[0], 200)
        self.assertEqual(api.handle_get("/api/evidencetrail/consistency/consistency-20000101-000000")[0], 404)
        self.assertEqual(api.handle_get("/api/evidencetrail/consistency/..")[0], 404)

    def test_the_api_cannot_start_or_change_a_report(self):
        for path in ("/api/evidencetrail/consistency", "/api/evidencetrail/consistency/consistency-20261001-100000"):
            self.assertEqual(api.handle_post(path, {})[0], 404)


if __name__ == "__main__":
    unittest.main()
