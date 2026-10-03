"""Tests for Demographic, KYC, Purpose, and Product scoring."""

import unittest
from engine.kyc_scorer import KYCScorer
from generator.customer_generator import CustomerGenerator
from models.customer import PEPStatus, AdverseMedia, SanctionStatus

class TestKYCScorer(unittest.TestCase):

    def setUp(self):
        self.scorer = KYCScorer()
        self.cg = CustomerGenerator(seed=202)

    def test_clean_low_risk_kyc(self):
        cust = self.cg.generate_customer("CUST-CLEAN", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        pillar = self.scorer.score_demographic_kyc(cust)
        self.assertLess(pillar.raw_score, 35.0)
        self.assertEqual(pillar.weight, 0.30)
        self.assertTrue(any("Clean" in f for f in pillar.contributing_factors))

    def test_foreign_pep_kyc_elevation(self):
        cust = self.cg.generate_customer("CUST-PEP", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        cust.pep_status = PEPStatus.FOREIGN_PEP
        pillar = self.scorer.score_demographic_kyc(cust)
        self.assertGreaterEqual(pillar.raw_score, 50.0)
        self.assertTrue(any("Foreign PEP" in f for f in pillar.contributing_factors))

    def test_adverse_media_financial_crime(self):
        cust = self.cg.generate_customer("CUST-ADV", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        cust.adverse_media = AdverseMedia.FINANCIAL_CRIME
        cust.adverse_media_details = "Indictment for cross-border money laundering scheme"
        pillar = self.scorer.score_demographic_kyc(cust)
        self.assertGreaterEqual(pillar.raw_score, 55.0)
        self.assertTrue(any("Financial Crime" in f for f in pillar.contributing_factors))

    def test_high_risk_occupation_scoring(self):
        cust = self.cg.generate_customer("CUST-OCC", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        cust.occupation_risk_key = "CASINO_OPERATOR"
        cust.occupation = "Casino Operator"
        pillar = self.scorer.score_demographic_kyc(cust)
        self.assertGreaterEqual(pillar.raw_score, 45.0)

    def test_purpose_and_wealth_plausibility(self):
        cust = self.cg.generate_customer("CUST-PURP", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        # Normal
        pillar_norm = self.scorer.score_purpose_and_nature(cust)
        self.assertLess(pillar_norm.raw_score, 30.0)

        # Extreme wealth disparity (student with $10M net worth and $10k income)
        cust.annual_income_usd = 10000.0
        cust.net_worth_usd = 10000000.0
        cust.source_of_wealth = "Cash holdings"
        cust.declared_purpose_nature = "CRYPTO_ASSET_TRADING"
        pillar_implausible = self.scorer.score_purpose_and_nature(cust)
        self.assertGreaterEqual(pillar_implausible.raw_score, 50.0)

    def test_products_and_channel_risk(self):
        cust = self.cg.generate_customer("CUST-PROD", archetype_name="DOMESTIC_SALARIED_LOW_RISK")
        cust.products_held = ["CURRENT_ACCOUNT", "CRYPTO_GATEWAY_ACCESS", "INTERNATIONAL_WIRE_SERVICE"]
        cust.onboarding_channel = "THIRD_PARTY_INTRODUCER"
        pillar = self.scorer.score_products_and_channels(cust)
        self.assertGreater(pillar.raw_score, 50.0)

if __name__ == "__main__":
    unittest.main()
