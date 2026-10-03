"""ADK request filtering: drop other specialists' raw tool dumps, keep findings, keep own tool exchanges."""

import unittest

import _no_live_keys  # noqa: F401

from google.genai import types

from app.context_callbacks import _drop_other_transcripts, columnar

HEADER = "For context: below is a transcript of what another agent did, quoted back to you."


def text(role, value):
    return types.Content(role=role, parts=[types.Part.from_text(text=value)])


def convo():
    return [
        text("user", "Investigate customer CUST-1."),
        types.Content(role="user", parts=[types.Part.from_text(text=HEADER),
                                          types.Part.from_text(text="[customer_agent] called tool `get_customer_profile` with parameters: <<<x>>>")]),
        types.Content(role="user", parts=[types.Part.from_text(text=HEADER),
                                          types.Part.from_text(text="[transaction_agent] `get_transactions` tool returned result: <<<" + "x" * 5000 + ">>>")]),
        types.Content(role="user", parts=[types.Part.from_text(text=HEADER),
                                          types.Part.from_text(text="[transaction_agent] said: <<<BEGIN>>> findings: TXN-1 for 9800.00")]),
        types.Content(role="model", parts=[types.Part.from_function_call(name="get_ownership", args={"customer_id": "CUST-1"})]),
        types.Content(role="user", parts=[types.Part.from_function_response(name="get_ownership", response={"ok": 1})]),
    ]


def flat(contents):
    return [p.text or ("CALL" if p.function_call else "RESP" if p.function_response else "") for c in contents for p in c.parts]


class Filtering(unittest.TestCase):
    def test_a_specialist_loses_other_agents_tool_dumps_but_keeps_their_findings(self):
        out = flat(_drop_other_transcripts(convo(), "ownership_agent"))
        self.assertFalse(any("get_transactions" in t or "get_customer_profile" in t for t in out))
        self.assertTrue(any("TXN-1 for 9800.00" in t for t in out))      # findings stay, exact
        self.assertIn("Investigate customer CUST-1.", out)
        self.assertEqual(out.count("CALL"), 1)                            # its own tool exchange is untouched
        self.assertEqual(out.count("RESP"), 1)

    def test_the_consolidator_drops_all_specialist_transcripts_because_findings_come_from_state(self):
        out = flat(_drop_other_transcripts(convo(), "consolidator_agent"))
        self.assertFalse(any(t.startswith("[") or t.startswith("For context") for t in out))

    def test_an_agents_own_earlier_transcript_text_is_never_dropped(self):
        out = flat(_drop_other_transcripts(convo(), "transaction_agent"))
        self.assertTrue(any("get_transactions" in t for t in out))

    def test_orphan_headers_are_removed(self):
        out = flat(_drop_other_transcripts(convo(), "ownership_agent"))
        self.assertEqual(sum(t.startswith("For context") for t in out), 1)   # only the one before the kept finding

    def test_the_input_is_not_required_to_have_other_agents(self):
        only = [text("user", "hello")]
        self.assertEqual(flat(_drop_other_transcripts(only, "customer_agent")), ["hello"])


class Columnar(unittest.TestCase):
    def test_uniform_records_become_columns_losslessly(self):
        rows = [{"id": f"TXN-{i}", "amount": i * 1.5, "note": None} for i in range(6)]
        packed = columnar({"result": rows})["result"]
        rebuilt = [dict(zip(packed["_columns"], r)) for r in packed["_rows"]]
        self.assertEqual(rebuilt, rows)

    def test_short_or_irregular_lists_are_left_alone(self):
        short = [{"a": 1}, {"a": 2}]
        self.assertEqual(columnar(short), short)
        irregular = [{"a": i} if i % 2 else {"b": i} for i in range(8)]
        self.assertEqual(columnar(irregular), irregular)

    def test_scalars_and_nested_values_pass_through(self):
        self.assertEqual(columnar({"x": [1, 2, 3], "y": {"z": "w"}}), {"x": [1, 2, 3], "y": {"z": "w"}})


if __name__ == "__main__":
    unittest.main()
