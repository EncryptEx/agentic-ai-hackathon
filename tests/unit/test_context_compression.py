"""Context compression must be fail-open, never alter exact facts, and never reach the live API from tests."""

import io
import json
import os
import unittest
from unittest import mock

import _no_live_keys  # noqa: F401  (kill switch for live providers)

from app import context_compression as cc

LONG = ("The customer sent TXN-0042 for 9800.00 USD to Escrow Ltd on 2026-09-19. "
        "The payee is unverified and the source of funds is unknown. ") * 12


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def condense_reply(transform):
    def urlopen(request, timeout=None):
        body = json.loads(request.data)
        urlopen.calls.append(body)
        return FakeResponse(json.dumps({"messages": [
            {"role": "user", "content": transform(m["content"])} for m in body["messages"]]}).encode())
    urlopen.calls = []
    return urlopen


ENV = {"CONDENSE_ENABLED": "1", "CONDENSE_API_KEY": "test-key", "EVIDENCETRAIL_DISABLE_LIVE": "0",
       "CONDENSE_MIN_CHARS": "200"}


class Compress(unittest.TestCase):
    def run_with(self, urlopen, texts, env=None):
        with mock.patch.dict(os.environ, {**ENV, **(env or {})}), \
                mock.patch.object(cc.urllib.request, "urlopen", urlopen):
            comp = cc.ContextCompressor()
            return comp, comp.compress(texts)

    def test_disabled_by_default_and_no_call(self):
        urlopen = condense_reply(lambda t: t)
        with mock.patch.dict(os.environ, {"CONDENSE_ENABLED": "0"}), \
                mock.patch.object(cc.urllib.request, "urlopen", urlopen):
            out, stats = cc.ContextCompressor().compress([LONG])
        self.assertEqual(out, [LONG])
        self.assertEqual(stats["status"], "disabled")
        self.assertEqual(urlopen.calls, [])

    def test_the_test_kill_switch_blocks_live_calls(self):
        urlopen = condense_reply(lambda t: t)
        _, (out, stats) = self.run_with(urlopen, [LONG], {"EVIDENCETRAIL_DISABLE_LIVE": "1"})
        self.assertEqual(stats["status"], "live_disabled")
        self.assertEqual(urlopen.calls, [])

    def test_missing_key_falls_back(self):
        urlopen = condense_reply(lambda t: t)
        with mock.patch.dict(os.environ, {**ENV}), mock.patch.object(cc.urllib.request, "urlopen", urlopen):
            os.environ.pop("CONDENSE_API_KEY")
            out, stats = cc.ContextCompressor().compress([LONG])
        self.assertEqual((out, stats["status"]), ([LONG], "missing_key"))

    def test_small_texts_are_never_sent(self):
        urlopen = condense_reply(lambda t: t)
        _, (out, stats) = self.run_with(urlopen, ["short text"])
        self.assertEqual(out, ["short text"])
        self.assertEqual(urlopen.calls, [])

    def test_a_valid_compaction_is_used_and_batched_in_one_call(self):
        shorter = lambda t: t.replace("customer sent ", "customer ")
        urlopen = condense_reply(shorter)
        other = LONG.replace("9800.00", "9800.01") + " Extra detail."
        _, (out, stats) = self.run_with(urlopen, [LONG, other])
        self.assertEqual(len(urlopen.calls), 1)
        self.assertEqual(len(urlopen.calls[0]["messages"]), 2)
        self.assertEqual(stats["accepted"], 2)
        self.assertLess(len(out[0]), len(LONG))

    def test_a_compaction_that_changes_a_number_is_rejected(self):
        urlopen = condense_reply(lambda t: t.replace("9800.00", "980.00"))
        _, (out, stats) = self.run_with(urlopen, [LONG])
        self.assertEqual(out, [LONG])
        self.assertEqual(stats["rejected"], 1)

    def test_a_compaction_that_drops_a_caution_sentence_is_rejected(self):
        urlopen = condense_reply(lambda t: t.replace("The payee is unverified and the source of funds is unknown. ", ""))
        _, (out, stats) = self.run_with(urlopen, [LONG])
        self.assertEqual(out, [LONG])
        self.assertEqual(stats["rejected"], 1)

    def test_invented_words_are_rejected(self):
        urlopen = condense_reply(lambda t: t.replace("Escrow Ltd", "Escrow") + " Confirmed fraud.")
        _, (out, _) = self.run_with(urlopen, [LONG])
        self.assertEqual(out, [LONG])

    def test_a_failing_provider_returns_originals_and_opens_the_circuit(self):
        def boom(request, timeout=None):
            boom.calls += 1
            raise OSError("down")
        boom.calls = 0
        comp, (out, stats) = self.run_with(boom, [LONG])
        self.assertEqual((out, stats["status"]), ([LONG], "fallback"))
        with mock.patch.dict(os.environ, {**ENV}), mock.patch.object(cc.urllib.request, "urlopen", boom):
            out2, stats2 = comp.compress([LONG + " more"])
        self.assertEqual(boom.calls, 1)  # one failure stops further attempts for this run
        self.assertEqual(stats2["status"], "circuit_open")
        self.assertEqual(out2, [LONG + " more"])

    def test_malformed_response_falls_back(self):
        def bad(request, timeout=None):
            return FakeResponse(b'{"messages": "nope"}')
        _, (out, stats) = self.run_with(bad, [LONG])
        self.assertEqual((out, stats["status"]), ([LONG], "fallback"))

    def test_repeats_come_from_the_cache(self):
        urlopen = condense_reply(lambda t: t.replace("customer sent ", "customer "))
        comp, _ = self.run_with(urlopen, [LONG])
        with mock.patch.dict(os.environ, {**ENV}), mock.patch.object(cc.urllib.request, "urlopen", urlopen):
            out, stats = comp.compress([LONG])
        self.assertEqual(len(urlopen.calls), 1)
        self.assertEqual(stats["cache_hits"], 1)

    def test_secret_never_appears_in_stats(self):
        urlopen = condense_reply(lambda t: t)
        _, (_, stats) = self.run_with(urlopen, [LONG])
        self.assertNotIn("test-key", json.dumps(stats))


class Interactions(unittest.TestCase):
    def steps(self, payload_text):
        return [
            {"type": "user_input", "content": [{"type": "text", "text": "Investigate"}]},
            {"type": "function_call", "id": "call-1", "name": "tool_a", "arguments": {"id": "EV-001"},
             "signature": "SIG-A"},
            {"type": "function_result", "call_id": "call-1",
             "result": [{"type": "text", "text": json.dumps({"summary": payload_text, "amount": 9800.0})}]},
            {"type": "function_call", "id": "call-2", "name": "tool_b", "arguments": {}, "signature": "SIG-B"},
            {"type": "function_result", "call_id": "call-2",
             "result": [{"type": "text", "text": json.dumps({"summary": payload_text})}]},
        ]

    def test_only_older_results_are_touched_and_originals_are_not_mutated(self):
        steps = self.steps(LONG)
        snapshot = json.dumps(steps, sort_keys=True)
        urlopen = condense_reply(lambda t: t.replace("customer sent ", "customer "))
        with mock.patch.dict(os.environ, ENV), mock.patch.object(cc.urllib.request, "urlopen", urlopen):
            out, stats = cc.prepare_interactions(steps, cc.ContextCompressor())
        self.assertEqual(json.dumps(steps, sort_keys=True), snapshot)
        self.assertEqual(out[1], steps[1])                  # call, id and signature exact
        self.assertEqual(out[3], steps[3])
        self.assertEqual(out[4], steps[4])                  # latest result exact
        old = json.loads(out[2]["result"][0]["text"])
        self.assertEqual(old["amount"], 9800.0)
        self.assertLess(len(old["summary"]), len(LONG))
        self.assertLess(stats["after_bytes"], stats["before_bytes"])

    def test_without_condense_the_payloads_are_value_identical(self):
        steps = self.steps(LONG)
        with mock.patch.dict(os.environ, {"CONDENSE_ENABLED": "0"}):
            out, _ = cc.prepare_interactions(steps, cc.ContextCompressor())
        self.assertEqual(json.loads(out[2]["result"][0]["text"]), json.loads(steps[2]["result"][0]["text"]))


if __name__ == "__main__":
    unittest.main()
