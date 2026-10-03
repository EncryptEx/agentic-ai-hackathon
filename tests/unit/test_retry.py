"""Transient provider failures are retried; real errors are not; exhausted retries stay visible."""

import io
import json
import unittest
import urllib.error

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)

from evidencetrail import gemini as gemini_mod
from evidencetrail import jev as jev_mod
from evidencetrail.jev import ProviderUnavailable, post_json_with_retry


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, body='{"error": {"message": "nope"}}'):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(body.encode()))


class Scripted:
    """Stands in for urllib.request.urlopen: plays a list of outcomes (exceptions are raised, dicts returned)."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


class RetryBehaviour(unittest.TestCase):
    def setUp(self):
        self._urlopen, self._sleep = jev_mod.urllib.request.urlopen, jev_mod._sleep
        self.sleeps = []
        jev_mod._sleep = self.sleeps.append  # no real waiting in tests

    def tearDown(self):
        jev_mod.urllib.request.urlopen, jev_mod._sleep = self._urlopen, self._sleep

    def _post(self, outcomes, **kw):
        scripted = Scripted(outcomes)
        jev_mod.urllib.request.urlopen = scripted
        try:
            return post_json_with_retry(lambda: object(), "sk-secret", "Gemini", **kw), scripted
        except ProviderUnavailable as e:
            return e, scripted

    def test_a_timeout_then_success_is_recovered_with_backoff(self):
        out, s = self._post([TimeoutError(), {"ok": 1}])
        self.assertEqual((out, s.calls), ({"ok": 1}, 2))
        self.assertEqual(self.sleeps, [1.5])

    def test_rate_limit_and_server_errors_are_retried(self):
        for code in (429, 500, 503):
            self.sleeps.clear()
            out, s = self._post([http_error(code), {"ok": code}])
            self.assertEqual((out, s.calls), ({"ok": code}, 2), code)

    def test_connection_errors_are_retried(self):
        out, s = self._post([urllib.error.URLError("reset"), ConnectionError(), {"ok": 1}])
        self.assertEqual((out, s.calls), ({"ok": 1}, 3))
        self.assertEqual(self.sleeps, [1.5, 3.0])

    def test_real_errors_fail_immediately_without_retrying(self):
        for code in (400, 401, 403, 404):
            out, s = self._post([http_error(code)])
            self.assertIsInstance(out, ProviderUnavailable)
            self.assertEqual(s.calls, 1, code)
            self.assertIn(f"HTTP {code}", str(out))
        self.assertEqual(self.sleeps, [])

    def test_exhausted_retries_raise_a_visible_error_that_says_so(self):
        out, s = self._post([TimeoutError(), TimeoutError(), TimeoutError()])
        self.assertIsInstance(out, ProviderUnavailable)
        self.assertEqual(s.calls, 3)
        self.assertIn("after 3 attempts", str(out))
        self.assertIn("TimeoutError", str(out))
        out, s = self._post([http_error(503), http_error(503), http_error(503)])
        self.assertIn("HTTP 503", str(out))
        self.assertIn("after 3 attempts", str(out))

    def test_bad_json_is_not_retried(self):
        class Garbage(FakeResponse):
            def __init__(self):
                self._body = b"not json"
        scripted = Scripted([])
        scripted.__call__ = None
        jev_mod.urllib.request.urlopen = lambda req, timeout=None: Garbage()
        with self.assertRaises(ProviderUnavailable) as ctx:
            post_json_with_retry(lambda: object(), "k", "Jev")
        self.assertIn("request failed", str(ctx.exception))
        self.assertEqual(self.sleeps, [])

    def test_the_key_never_appears_in_errors(self):
        body = json.dumps({"error": {"message": "invalid key sk-secret"}})
        out, _ = self._post([http_error(400, body)])
        self.assertNotIn("sk-secret", str(out))

    def test_both_clients_use_the_retry_helper(self):
        import inspect
        self.assertIn("post_json_with_retry", inspect.getsource(gemini_mod.GeminiClient.generate))
        self.assertIn("post_json_with_retry", inspect.getsource(jev_mod.JevClient.assess))

    def test_a_flaky_gemini_call_succeeds_end_to_end_after_a_timeout(self):
        import os
        os.environ["EVIDENCETRAIL_DISABLE_LIVE"] = "0"
        os.environ["GEMINI_API_KEY"] = "sk-test"
        try:
            reply = {"steps": [{"type": "model_output", "content": "hello"}], "model": "m1"}
            jev_mod.urllib.request.urlopen = Scripted([TimeoutError(), reply])
            turn = gemini_mod.GeminiClient().generate("sys", [{"type": "user_input", "content": "hi"}], [])
        finally:
            os.environ["EVIDENCETRAIL_DISABLE_LIVE"] = "1"
            del os.environ["GEMINI_API_KEY"]
        self.assertEqual((turn.text, turn.returned_model_version), ("hello", "m1"))


if __name__ == "__main__":
    unittest.main()
