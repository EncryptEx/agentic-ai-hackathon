"""End-to-end tests for composite Risk Engine."""

import unittest
from datetime import datetime, timedelta
from engine.risk_engine import RiskEngine
from generator.customer_generator import CustomerGenerator
from generator.transaction_generator import TransactionGenerator
from models.customer import SanctionStatus, PEPStatus, AdverseMedia
from models.risk_score import RiskTier

class TestRiskEngine(unittest.TestCase):

    def setUp(self):
        self.engine = RiskEngine()
        self.cg = CustomerGenerator(seed=404)
        self.tg = TransactionGenerator(seed=404)

    def test_low_risk_customer_evaluation(self):
        cust = self.cg.generate_customer("CUST-LOW", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        txs = self.tg.generate_customer_transactions(cust, days_history=60)
        res = self.engine.evaluate_customer(cust, txs)

        self.assertEqual(res.risk_tier, RiskTier.LOW)
        self.assertLess(res.composite_score, 35.0)
        self.assertIn("STANDARD_DUE_DILIGENCE", res.recommended_action)
        self.assertGreater(len(res.action_checklist), 0)
        self.assertIsNotNone(res.executive_summary)

    def test_sanctions_hard_stop_override(self):
        cust = self.cg.generate_customer("CUST-SANC", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        cust.sanction_status = SanctionStatus.CONFIRMED_HIT
        res = self.engine.evaluate_customer(cust, [])

        self.assertEqual(res.risk_tier, RiskTier.CRITICAL)
        self.assertEqual(res.composite_score, 100.0)
        self.assertIn("FILE_SAR", res.recommended_action)

    def test_mule_archetype_evaluation(self):
        cust = self.cg.generate_customer("CUST-MULE", archetype_name="STUDENT_MONEY_MULE")
        txs = self.tg.generate_customer_transactions(cust, days_history=90)
        res = self.engine.evaluate_customer(cust, txs)

        self.assertEqual(res.risk_tier, RiskTier.CRITICAL)
        self.assertGreaterEqual(res.composite_score, 85.0)
        self.assertTrue(any(a.rule_id == "TM-02" for a in res.alerts))
        self.assertIn("FILE_SAR_AND_IMMEDIATE_ACCOUNT_RESTRICTION", res.recommended_action)

    def test_structuring_archetype_evaluation(self):
        cust = self.cg.generate_customer("CUST-STRUC", archetype_name="STRUCTURING_CASH_OPERATOR")
        txs = self.tg.generate_customer_transactions(cust, days_history=90)
        res = self.engine.evaluate_customer(cust, txs)

        self.assertIn(res.risk_tier, [RiskTier.HIGH, RiskTier.CRITICAL])
        self.assertGreaterEqual(res.composite_score, 75.0)
        self.assertTrue(any(a.rule_id == "TM-01" for a in res.alerts))

    def test_foreign_pep_mandatory_edd(self):
        cust = self.cg.generate_customer("CUST-FPEP", archetype_name="FOREIGN_PEP_ASSOCIATE")
        res = self.engine.evaluate_customer(cust, [])

        self.assertIn(res.risk_tier, [RiskTier.HIGH, RiskTier.CRITICAL])
        self.assertGreaterEqual(res.composite_score, 65.0)
        self.assertIn("ENHANCED_DUE_DILIGENCE", res.recommended_action)

if __name__ == "__main__":
    unittest.main()
