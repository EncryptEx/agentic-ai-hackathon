"""Tests for Customer and Transaction generation."""

import unittest
from datetime import datetime
from generator.customer_generator import CustomerGenerator, ARCHETYPE_CONFIGS
from generator.transaction_generator import TransactionGenerator
from models.customer import CustomerProfile, PEPStatus, AdverseMedia
from models.transaction import Transaction

class TestGenerators(unittest.TestCase):

    def setUp(self):
        self.cg = CustomerGenerator(seed=101)
        self.tg = TransactionGenerator(seed=101)

    def test_customer_generation_fields(self):
        cust = self.cg.generate_customer("CUST-TEST-001")
        self.assertIsInstance(cust, CustomerProfile)
        self.assertEqual(cust.customer_id, "CUST-TEST-001")
        self.assertTrue(18 <= cust.age <= 95)
        self.assertGreater(cust.annual_income_usd, 0)
        self.assertGreater(cust.net_worth_usd, 0)
        self.assertGreater(cust.declared_expected_monthly_turnover_usd, 0)
        self.assertGreater(cust.declared_expected_max_single_tx_usd, 0)
        self.assertIn("CURRENT_ACCOUNT", cust.products_held)
        self.assertIsNotNone(cust.citizenship)
        self.assertIsNotNone(cust.residence_country)

    def test_customer_archetypes(self):
        for arch in ARCHETYPE_CONFIGS.keys():
            cust = self.cg.generate_customer(f"CUST-{arch[:4]}", archetype_name=arch)
            self.assertEqual(cust.archetype, arch)
            if arch == "STUDENT_MONEY_MULE":
                self.assertEqual(cust.occupation, "Student")
                self.assertTrue(18 <= cust.age <= 25)
            elif arch == "RETIRED_PENSIONER":
                self.assertEqual(cust.occupation, "Retired Pensioner")
                self.assertTrue(cust.age >= 65)
            elif arch == "DOMESTIC_PEP_OFFICIAL":
                self.assertEqual(cust.pep_status, PEPStatus.DOMESTIC_PEP)
            elif arch == "ADVERSE_MEDIA_FINANCIAL_CRIME":
                self.assertEqual(cust.adverse_media, AdverseMedia.FINANCIAL_CRIME)

    def test_customer_batch_generation(self):
        batch = self.cg.generate_batch(count=25)
        self.assertEqual(len(batch), 25)
        ids = [c.customer_id for c in batch]
        self.assertEqual(len(ids), len(set(ids))) # All unique

    def test_transaction_generation_integrity(self):
        cust = self.cg.generate_customer("CUST-TX-001", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        txs = self.tg.generate_customer_transactions(cust, days_history=60)
        self.assertGreater(len(txs), 10)

        # Check chronological order
        timestamps = [datetime.fromisoformat(t.timestamp) for t in txs]
        self.assertEqual(timestamps, sorted(timestamps))

        # Check transaction attributes
        for t in txs:
            self.assertEqual(t.customer_id, cust.customer_id)
            self.assertGreater(t.amount_usd, 0)
            self.assertIn(t.direction.value, ["INBOUND", "OUTBOUND"])

    def test_suspicious_typology_injection(self):
        # Structuring archetype
        cust_struct = self.cg.generate_customer("CUST-S", archetype_name="STRUCTURING_CASH_OPERATOR")
        txs_struct = self.tg.generate_customer_transactions(cust_struct, days_history=90)
        struct_injected = [t for t in txs_struct if t.synthetic_typology_tag == "STRUCTURING_SMURFING"]
        self.assertGreaterEqual(len(struct_injected), 3)

        # Mule archetype
        cust_mule = self.cg.generate_customer("CUST-M", archetype_name="STUDENT_MONEY_MULE")
        txs_mule = self.tg.generate_customer_transactions(cust_mule, days_history=90)
        mule_inflows = [t for t in txs_mule if t.synthetic_typology_tag == "MULE_INBOUND_SPIKE"]
        mule_outflows = [t for t in txs_mule if t.synthetic_typology_tag == "MULE_RAPID_DISSIPATION"]
        self.assertGreaterEqual(len(mule_inflows), 1)
        self.assertGreaterEqual(len(mule_outflows), 1)

if __name__ == "__main__":
    unittest.main()
