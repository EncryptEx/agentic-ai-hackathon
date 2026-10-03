"""FRAML data-seed adapter: evidence shapes, no answer-key leakage, no look-ahead, and batch scoring."""

import json
import os
import re
import time
import unittest

import _no_live_keys  # noqa: F401  (strips real provider keys loaded from .env)

from evidencetrail import api, policy, seed as seed_mod
from evidencetrail.alerts import AlertStore
from evidencetrail.experiments import gather_all, rules_baseline
from evidencetrail.runs import RunManager
from evidencetrail.scenarios import apply_counterfactual, get_case
from evidencetrail.seed import CASE_PREFIX, get_seed, pseudo, recipient_id, slug
from test_evidencetrail import FakeJev
from test_team import AutoTeam

SEED = get_seed()
HAVE_SEED = SEED.available()

# tx ids from the committed seed (the generator is seeded, so they are stable)
DRAIN_4 = "TXN-0100287"      # CUST-00004: high-value drain on a device shared with other customers
PROBE_1 = "TXN-0100285"      # CUST-00004: the very first micro charge of that ring
APP_FIRST = "TXN-0102875"    # CUST-00043: first transfer to a brand-new payee
ATO = "TXN-0103005"          # CUST-00045: international wire after a rapid country change
LANDLORD = "TXN-0106373"     # CUST-00097: large ACH to a landlord paid by every customer at once

LEAK_WORDS = ("APP_INVESTMENT_SCAM", "CARD_TESTING", "CARD_FRAUD", "MULE_", "BOTNET", "STRUCTURING", "DORMANCY",
              "ATO_IMPOSSIBLE", "fraud_typology", "is_fraud", "is_suspicious", "synthetic_typology")


@unittest.skipUnless(HAVE_SEED, "data/kyc_aml.db is not available")
class CaseShape(unittest.TestCase):
    def test_case_has_the_same_structure_as_a_scenario(self):
        case = get_case(CASE_PREFIX + DRAIN_4)
        self.assertEqual(case["case_id"], CASE_PREFIX + DRAIN_4)
        self.assertEqual(set(case["world"]), {"behavior", "device", "recipients", "graph", "tool_failures"})
        tx = case["transaction"]
        self.assertEqual((tx["customer_id"], tx["currency"], tx["amount"]), ("CUST-00004", "USD", 4610.79))
        self.assertIn(tx["recipient_id"], case["world"]["recipients"])
        self.assertIn(tx["recipient_id"], case["world"]["graph"])

    def test_unknown_inbound_or_non_seed_ids_give_no_case(self):
        self.assertIsNone(get_case(CASE_PREFIX + "TXN-DOES-NOT-EXIST"))
        inbound = next(r["transaction_id"] for r in SEED.by_id.values() if r["direction"] == "INBOUND")
        self.assertIsNone(get_case(CASE_PREFIX + inbound))
        self.assertIsNone(get_case("not-a-case"))

    def test_the_four_tools_work_unchanged_on_a_seed_case(self):
        store = gather_all(get_case(CASE_PREFIX + DRAIN_4))
        self.assertEqual(sorted(e["type"] for e in store.all()),
                         ["behavior_profile", "device_inspection", "recipient_inspection", "relationship_graph"])

    def test_behavior_range_comes_from_prior_history_only(self):
        b = get_case(CASE_PREFIX + DRAIN_4)["world"]["behavior"]
        self.assertGreater(4610.79, b["typical_amount_max"])           # clearly out of the customer's range
        self.assertGreaterEqual(b["typical_amount_min"], 0)
        self.assertNotIn("RCP-LUXE-HIGH-END-ELECTRONICS-DIRECT", b["known_recipient_ids"])  # never paid before
        self.assertIn("recent_inbound_48h", b)

    def test_device_evidence_flags_the_unfamiliar_shared_device(self):
        d = get_case(CASE_PREFIX + DRAIN_4)["world"]["device"]
        self.assertFalse(d["device_known"])
        types = {a["type"]: a["severity"] for a in d["session_anomalies"]}
        self.assertEqual(types["follows_micro_charge_probing"], "meaningful")
        self.assertEqual(types["ip_country_differs_from_profile"], "minor")

    def test_rapid_country_change_is_detected_for_the_takeover_wire(self):
        d = get_case(CASE_PREFIX + ATO)["world"]["device"]
        self.assertTrue(any(a["type"] == "rapid_country_change" and a["severity"] == "meaningful"
                            for a in d["session_anomalies"]))
        self.assertEqual(rules_baseline(get_case(CASE_PREFIX + ATO))["final"]["simulated_action"], "REVIEW")

    def test_channels_without_telemetry_are_not_treated_as_a_new_device(self):
        no_dev = next(r for r in SEED.by_id.values() if r["direction"] == "OUTBOUND" and not r["device_id"])
        d = get_case(CASE_PREFIX + no_dev["transaction_id"])["world"]["device"]
        self.assertFalse(d["telemetry_available"])
        self.assertNotIn("device_known", d)
        self.assertEqual(policy.derive_signals(gather_all(get_case(CASE_PREFIX + no_dev["transaction_id"])),
                                               get_case(CASE_PREFIX + no_dev["transaction_id"])["transaction"])["device_compromise"], None)


@unittest.skipUnless(HAVE_SEED, "data/kyc_aml.db is not available")
class NoAnswerKeyLeakage(unittest.TestCase):
    def test_no_case_the_agents_can_see_contains_label_words(self):
        for c in SEED.candidates():
            blob = json.dumps(get_case(c["case_id"]))
            for word in LEAK_WORDS:
                self.assertNotIn(word, blob, f"{c['case_id']} leaks {word}")

    def test_device_ids_are_pseudonymised_and_stable(self):
        d = get_case(CASE_PREFIX + DRAIN_4)["world"]["device"]
        self.assertRegex(d["device_ref"], r"^DEV-[0-9A-F]{6}$")
        self.assertEqual(d["device_ref"], pseudo("DEV", "DEV-BOTNET-CLONE-441"))
        self.assertNotIn("BOTNET", json.dumps(get_case(CASE_PREFIX + DRAIN_4)))

    def test_label_columns_are_never_selected_by_the_adapter(self):
        src = open(seed_mod.__file__, encoding="utf-8").read()
        for column in ("is_fraud_synthetic", "fraud_typology_tag", "is_suspicious_synthetic", "synthetic_typology_tag"):
            self.assertNotIn(column, src)

    def test_only_evaluator_modules_import_the_label_module(self):
        pkg = os.path.dirname(seed_mod.__file__)
        importers = {f for f in os.listdir(pkg) if f.endswith(".py") and f != "seed_labels.py"
                     and re.search(r"seed_labels", open(os.path.join(pkg, f), encoding="utf-8").read())}
        self.assertEqual(importers, {"metrics.py", "experiments.py", "runs.py"})

    def test_candidate_picker_exposes_no_labels_and_is_deterministic(self):
        a, b = SEED.candidates(), SEED.candidates()
        self.assertEqual([c["case_id"] for c in a], [c["case_id"] for c in b])
        self.assertEqual(len(a), 58)
        for c in a:
            self.assertEqual(set(c), {"case_id", "synthetic", "name", "transaction"})
            self.assertNotIn("tag", json.dumps(c).lower().replace("transaction", ""))


@unittest.skipUnless(HAVE_SEED, "data/kyc_aml.db is not available")
class TimeCausality(unittest.TestCase):
    def test_the_first_event_of_a_ring_knows_nothing_about_the_ring(self):
        case = get_case(CASE_PREFIX + PROBE_1)
        rec = next(iter(case["world"]["recipients"].values()))
        self.assertEqual(rec["incoming_transfers_last_90_min"], 0)
        self.assertEqual(rec["prior_synthetic_flags"], 0)
        self.assertTrue(all(not n["synthetic_flag"] for n in case["world"]["graph"][case["transaction"]["recipient_id"]]["nodes"]))

    def test_a_customer_becomes_flagged_only_after_the_alerts_supporting_transactions(self):
        SEED._load()
        probe, drain = SEED.by_id[PROBE_1]["dt"], SEED.by_id[DRAIN_4]["dt"]
        self.assertFalse(SEED.flagged_before("CUST-00004", probe))
        self.assertTrue(SEED.flagged_before("CUST-00004", drain.replace(second=drain.second + 1) if drain.second < 59 else drain.replace(minute=drain.minute + 1)))

    def test_later_ring_members_do_see_the_earlier_ones(self):
        later = get_case(CASE_PREFIX + "TXN-0106563")  # fifth victim's second transfer to the same payee
        rec = next(iter(later["world"]["recipients"].values()))
        self.assertGreaterEqual(rec["distinct_other_payers_before"], 4)
        self.assertGreater(rec["prior_synthetic_flags"], 0)

    def test_history_never_includes_the_transaction_itself_or_anything_later(self):
        for tid in (DRAIN_4, APP_FIRST, ATO):
            tx = SEED.by_id[tid]
            known = get_case(CASE_PREFIX + tid)["world"]["behavior"]["known_recipient_ids"]
            later = {recipient_id(r["counterparty_name"]) for r in SEED.by_customer[tx["customer_id"]]
                     if r["dt"] >= tx["dt"] and r["direction"] == "OUTBOUND"}
            earlier = {recipient_id(r["counterparty_name"]) for r in SEED.by_customer[tx["customer_id"]]
                       if r["dt"] < tx["dt"] and r["direction"] == "OUTBOUND"}
            self.assertEqual(set(known), earlier)
            self.assertTrue((later - earlier) & {recipient_id(tx["counterparty_name"])})  # the payee really is new


@unittest.skipUnless(HAVE_SEED, "data/kyc_aml.db is not available")
class MappingFlawsFound(unittest.TestCase):
    """Regression guards for two flaws found when running policy v1 over the seed."""

    def test_a_recipient_without_a_recorded_age_is_unknown_not_newborn(self):
        rec = next(iter(get_case(CASE_PREFIX + LANDLORD)["world"]["recipients"].values()))
        self.assertIsNone(rec["account_age_days"])             # only new payees carry a true age
        self.assertGreaterEqual(rec["incoming_transfers_last_90_min"], 10)  # a synchronized burst that must not look like a mule
        store = gather_all(get_case(CASE_PREFIX + LANDLORD))
        sig = policy.derive_signals(store, get_case(CASE_PREFIX + LANDLORD)["transaction"])
        self.assertIsNone(sig["recipient_suspicious"])

    def test_new_payees_do_carry_a_true_age(self):
        rec = next(iter(get_case(CASE_PREFIX + APP_FIRST)["world"]["recipients"].values()))
        self.assertAlmostEqual(rec["account_age_days"], 0.5 / 24, places=2)

    def test_a_popular_merchant_is_not_suspicious_just_because_some_payer_was_flagged(self):
        rec = next(iter(get_case(CASE_PREFIX + LANDLORD)["world"]["recipients"].values()))
        num, den = (int(x) for x in rec["flagged_share_of_payers"].split("/"))
        self.assertGreater(num, 0)                  # some payers are flagged...
        self.assertEqual(rec["prior_synthetic_flags"], 0)   # ...but far below the share that means anything
        self.assertLess(num / den, seed_mod.FLAG_RATIO)

    def test_policy_treats_unknown_age_as_not_young(self):
        class S:
            def by_type(self, t):
                return [{"evidence_id": "EV-1", "payload": {"account_age_days": None, "incoming_transfers_last_90_min": 50,
                                                           "prior_synthetic_flags": 0}}] if t == "recipient_inspection" else []
        sig = policy.derive_signals(S(), {"amount": 1, "recipient_id": "x"})
        self.assertIsNone(sig["recipient_suspicious"])

    def test_rules_over_the_whole_sample_never_alarm_on_ordinary_spending(self):
        clean_alarms, caught = [], 0
        from evidencetrail.seed_labels import ground_truth
        for c in SEED.candidates():
            tid = c["transaction"]["transaction_id"]
            action = rules_baseline(get_case(c["case_id"]))["final"]["simulated_action"]
            if ground_truth(tid)["flagged"]:
                caught += action != "ALLOW"
            elif action != "ALLOW":
                clean_alarms.append(tid)
        self.assertEqual(clean_alarms, [])
        self.assertGreaterEqual(caught, 10)         # the rings are partly visible; early victims are not (time-causal)


@unittest.skipUnless(HAVE_SEED, "data/kyc_aml.db is not available")
class CounterfactualAndHandoff(unittest.TestCase):
    def test_counterfactual_patch_works_on_a_seed_case(self):
        case = get_case(CASE_PREFIX + "TXN-0106563")
        clone = apply_counterfactual(case, {"remove_network_links": True, "recipient": {"incoming_transfers_last_90_min": 0}})
        rid = case["transaction"]["recipient_id"]
        self.assertTrue(case["world"]["graph"][rid]["links"])
        self.assertEqual(clone["world"]["graph"][rid]["links"], [])

    def test_seed_customers_exist_in_the_framl_database_so_handoff_needs_no_manual_customer(self):
        from evidencetrail import handoff
        alert = {"transaction": {"customer_id": get_case(CASE_PREFIX + DRAIN_4)["transaction"]["customer_id"],
                                 "transaction_id": DRAIN_4}}
        self.assertFalse(handoff.customer_mismatch(alert, "CUST-00004"))
        self.assertIn("CUST-00004", SEED.customers)


@unittest.skipUnless(HAVE_SEED, "data/kyc_aml.db is not available")
class BatchAndApi(unittest.TestCase):
    def setUp(self):
        self.jev = FakeJev()
        self.mgr = RunManager(model_factory=AutoTeam, jev_factory=lambda: self.jev, alert_store=AlertStore(":memory:"))
        api.set_manager(self.mgr)

    def _wait(self, exp_id, tries=300):
        for _ in range(tries):
            _, exp = api.handle_get(f"/api/experiments/{exp_id}")
            if exp["state"] == "completed":
                return exp
            time.sleep(0.05)
        self.fail("batch did not finish")

    def test_picker_endpoint_lists_neutral_candidates(self):
        status, body = api.handle_get("/api/evidencetrail/seed/transactions")
        self.assertEqual((status, body["available"], body["total"]), (200, True, 58))
        self.assertTrue(all(i["case_id"].startswith(CASE_PREFIX) for i in body["items"]))

    def test_batch_scores_runs_against_the_answer_key_with_raw_counts(self):
        ids = [CASE_PREFIX + t for t in (DRAIN_4, APP_FIRST, ATO, LANDLORD, "TXN-0106563")]
        status, body = api.handle_post("/api/experiments/seed-batch", {"caseIds": ids})
        self.assertEqual(status, 202)
        s = self._wait(body["experimentId"])["summary"]
        self.assertEqual((s["attempted"], s["completed"], s["failed"], s["pending"]), (5, 5, 0, 0))
        self.assertEqual(s["answer_key_flagged"]["runs"], 4)
        self.assertEqual(s["answer_key_clean"]["runs"], 1)
        self.assertEqual(s["answer_key_clean"]["non_allow"], 0)        # the landlord payment is not alarming
        # ATO wire, the card drain (device first seen minutes earlier) and the later APP transfer are visible;
        # the first APP transfer to a brand-new payee is not (nothing is knowable yet).
        self.assertEqual(s["answer_key_flagged"]["non_allow"], 3)
        self.assertEqual(set(s["by_tag"]), {"CARD_FRAUD_HIGH_VALUE_DRAIN", "APP_INVESTMENT_SCAM", "ATO_IMPOSSIBLE_TRAVEL"})
        self.assertIn("never saw", s["note"])

    def test_batch_runs_triage_but_saves_no_alerts(self):
        status, body = api.handle_post("/api/experiments/seed-batch", {"caseIds": [CASE_PREFIX + ATO]})
        exp = self._wait(body["experimentId"])
        self.assertEqual(self.mgr.list_alerts(), [])
        self.assertEqual(len(self.jev.triage_states), 1)               # Jev triage did run
        row = exp["summary"]["rows"][0]
        self.assertEqual(row["alert_sources"], ["policy"])

    def test_unfinished_runs_are_pending_not_failures(self):
        from evidencetrail.experiments import summarize_seed_batch
        runs = [{"run_id": "r1", "case_id": CASE_PREFIX + ATO, "state": "queued"},
                {"run_id": "r2", "case_id": CASE_PREFIX + ATO, "state": "running"},
                {"run_id": "r3", "case_id": CASE_PREFIX + ATO, "state": "failed", "failure": "boom"}]
        s = summarize_seed_batch(runs)
        self.assertEqual((s["attempted"], s["completed"], s["failed"], s["pending"]), (3, 0, 1, 2))
        self.assertEqual(s["failures"], [{"run_id": "r3", "reason": "boom"}])

    def test_default_batch_takes_the_first_n_of_the_neutral_order_and_validates_input(self):
        status, body = api.handle_post("/api/experiments/seed-batch", {"limit": 3})
        self.assertEqual(status, 202)
        self.assertEqual(len(self._wait(body["experimentId"])["summary"]["rows"]), 3)
        self.assertEqual(api.handle_post("/api/experiments/seed-batch", {"limit": 0})[0], 400)
        self.assertEqual(api.handle_post("/api/experiments/seed-batch", {"caseIds": ["scenario-1"]})[0], 404)
        self.assertEqual(api.handle_post("/api/experiments/seed-batch", {"caseIds": "nope"})[0], 400)

    def test_finished_seed_run_exposes_the_answer_key_only_after_it_is_over(self):
        status, body = api.handle_post("/api/investigations", {"caseId": CASE_PREFIX + ATO})
        self.assertEqual(status, 202)
        self.assertNotIn("seed_ground_truth", self.mgr._runs[body["runId"]])      # never stored on the live run
        for _ in range(200):
            _, run = api.handle_get(f"/api/investigations/{body['runId']}")
            if run["state"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(run["seed_ground_truth"]["tag"], "ATO_IMPOSSIBLE_TRAVEL")
        self.assertEqual(run["alert"]["transaction"]["customer_id"], "CUST-00045")   # real FRAML customer -> hand-off ready

    def test_evaluation_compares_with_the_answer_key(self):
        from evidencetrail.metrics import deterministic_checks
        status, body = api.handle_post("/api/investigations", {"caseId": CASE_PREFIX + ATO})
        for _ in range(200):
            _, run = api.handle_get(f"/api/investigations/{body['runId']}")
            if run["state"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        check = deterministic_checks(run)["seed_check"]
        self.assertEqual((check["seed_tag"], check["seed_flagged"], check["system_flagged"], check["agrees"]),
                         ("ATO_IMPOSSIBLE_TRAVEL", True, True, True))


class SlugAndIds(unittest.TestCase):
    def test_recipient_ids_are_stable_and_readable(self):
        self.assertEqual(recipient_id("Luxe High-End Electronics Direct"), "RCP-LUXE-HIGH-END-ELECTRONICS-DIRECT")
        self.assertEqual(slug(""), "UNKNOWN")

    def test_a_missing_seed_database_degrades_to_unavailable(self):
        missing = seed_mod.SeedData(os.path.join(os.path.dirname(__file__), "nope.db"))
        self.assertFalse(missing.available())


if __name__ == "__main__":
    unittest.main()
