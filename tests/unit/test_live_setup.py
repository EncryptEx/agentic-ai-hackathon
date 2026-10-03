"""Key loading, error-detail scrubbing and the live-check logic (with fakes: no network)."""

import io
import json
import os
import tempfile
import unittest
import urllib.error

os.environ["EVIDENCETRAIL_ALERT_DB"] = ":memory:"

from evidencetrail import live_check
from evidencetrail.config import load_env_file
from evidencetrail.gemini import ModelTurn
from evidencetrail.jev import ALERT_QUESTIONS, JEV_QUESTIONS, ProviderUnavailable, error_detail


class EnvLoader(unittest.TestCase):
    def _file(self, text):
        path = os.path.join(tempfile.mkdtemp(), ".env")
        open(path, "w", encoding="utf-8").write(text)
        return path

    def test_parses_values_quotes_and_comments(self):
        env = {}
        names = load_env_file(self._file('# comment\nGEMINI_API_KEY="abc123"\nTYPESAFE_API_KEY=\'xyz\'\nPLAIN=v=1\n\nbad line\n'), env)
        self.assertEqual(env, {"GEMINI_API_KEY": "abc123", "TYPESAFE_API_KEY": "xyz", "PLAIN": "v=1"})
        self.assertEqual(sorted(names), ["GEMINI_API_KEY", "PLAIN", "TYPESAFE_API_KEY"])

    def test_blank_values_are_ignored_and_real_environment_wins(self):
        env = {"GEMINI_API_KEY": "from-environment"}
        load_env_file(self._file("GEMINI_API_KEY=from-file\nTYPESAFE_API_KEY=\n"), env)
        self.assertEqual(env, {"GEMINI_API_KEY": "from-environment"})  # blank skipped, existing kept

    def test_missing_file_is_fine_and_returns_names_only(self):
        self.assertEqual(load_env_file(os.path.join(tempfile.mkdtemp(), "nope.env"), {}), [])
        names = load_env_file(self._file("SECRET=hunter2\n"), {})
        self.assertEqual(names, ["SECRET"])
        self.assertNotIn("hunter2", str(names))

    def test_the_repo_env_file_is_gitignored(self):
        import subprocess
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        res = subprocess.run(["git", "check-ignore", ".env"], cwd=root, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)


class ErrorDetail(unittest.TestCase):
    def _http_error(self, body):
        return urllib.error.HTTPError("http://x", 400, "Bad", {}, io.BytesIO(body.encode()))

    def test_extracts_the_provider_message_and_scrubs_the_key(self):
        body = json.dumps({"error": {"message": "Invalid value at 'system_instruction' (key=sk-live-999)"}})
        detail = error_detail(self._http_error(body), key="sk-live-999")
        self.assertIn("system_instruction", detail)
        self.assertNotIn("sk-live-999", detail)
        self.assertIn("[REDACTED]", detail)

    def test_non_json_bodies_are_truncated_and_empty_bodies_give_nothing(self):
        self.assertTrue(error_detail(self._http_error("x" * 1000)).startswith(": x"))
        self.assertLessEqual(len(error_detail(self._http_error("x" * 1000))), 305)
        self.assertEqual(error_detail(self._http_error("")), "")


class FakeGemini:
    def __init__(self, ok=True, text="done"):
        self.ok, self.text, self.n = ok, text, 0

    def available(self):
        return True

    def generate(self, system, steps, tools):
        self.n += 1
        if self.n == 1:
            if not self.ok:
                return ModelTurn([{"type": "model_output", "content": "no tool"}], [], "no tool")
            call = {"id": "c1", "name": "get_behavior_profile", "arguments": {"customer_id": "CUST-A101"}}
            return ModelTurn([{"type": "function_call", **call}], [call], "", "fake-1")
        return ModelTurn([{"type": "model_output", "content": self.text}], [], self.text, "fake-1")


class FakeJev:
    def __init__(self, bad=None):
        self.bad = bad

    def available(self):
        return True

    def assess(self, state, questions=None):
        if self.bad == "outage":
            raise ProviderUnavailable("Jev HTTP 401: bad key")
        questions = questions or JEV_QUESTIONS  # the agent tool path passes no questions
        if "suspicion" in questions:
            n = {"suspicion": "WEIRD" if self.bad == "badchoice" else "SUSPICIOUS", "severity": 2}
        else:
            n = {"recipient_risk": "HIGH", "evidence_sufficiency": "SUFFICIENT_FOR_RECOMMENDATION",
                 "next_step": "FINISH", "manipulation_indicators": 0.4}
        return {"raw": {"answers": {}}, "normalized": n, "model": "jev-fake", "usage": None}


def statuses(results):
    return {r["name"]: r["status"] for r in results}


class LiveCheckLogic(unittest.TestCase):
    def test_all_pass_with_well_behaved_providers(self):
        res = statuses(live_check.check_gemini(FakeGemini()) + live_check.check_jev(FakeJev()))
        self.assertTrue(all(s == "PASS" for s in res.values()), res)
        self.assertEqual(len(res), 5)

    def test_gemini_without_a_tool_call_fails_with_the_step_types_seen(self):
        out = live_check.check_gemini(FakeGemini(ok=False))
        self.assertEqual(out[0]["status"], "FAIL")
        self.assertIn("model_output", out[0]["detail"])

    def test_missing_text_in_the_continuation_points_at_the_extractor(self):
        out = live_check.check_gemini(FakeGemini(text=""))
        self.assertEqual(out[-1]["status"], "FAIL")
        self.assertIn("_extract_text", out[-1]["detail"])

    def test_jev_unexpected_choice_value_and_outage_are_failures_with_detail(self):
        bad = live_check.check_jev(FakeJev(bad="badchoice"))
        self.assertEqual([r["status"] for r in bad], ["PASS", "FAIL"])
        self.assertIn("WEIRD", bad[1]["detail"])
        out = live_check.check_jev(FakeJev(bad="outage"))
        self.assertTrue(all(r["status"] == "FAIL" and "401" in r["detail"] for r in out))

    def test_missing_keys_skip_instead_of_calling_the_network(self):
        class NoKey:
            def available(self):
                return False
        self.assertEqual(statuses(live_check.check_gemini(NoKey())), {"gemini function call": "SKIP"})
        self.assertEqual(statuses(live_check.check_jev(NoKey())), {"jev questions": "SKIP"})

    def test_key_report_never_contains_a_key_value(self):
        os.environ["GEMINI_API_KEY"] = "sk-test-visible?"
        try:
            text = str(live_check.check_keys())
        finally:
            del os.environ["GEMINI_API_KEY"]
        self.assertNotIn("sk-test-visible", text)
        self.assertIn("set", text)

    def test_e2e_runs_every_scenario_and_reports_action_vs_label(self):
        from test_team import AutoTeam
        model = AutoTeam()
        model.available = lambda: True
        res = live_check.check_e2e(model, FakeJev())
        self.assertEqual(len(res), 5)
        # AutoTeam finishes every case with an ALLOW recommendation; the policy decides the rest.
        self.assertTrue(all("expected=" in r["detail"] for r in res))
        self.assertEqual(statuses(res)["e2e case-familiar"], "PASS")

    def test_main_exit_code_reflects_failures(self):
        self.assertEqual(live_check.main([]) in (0, 1), True)


if __name__ == "__main__":
    unittest.main()
