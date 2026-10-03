"""Tests for Fraud Detection Engine (ATO, Card Testing, APP Scams, Bust-Out, Synthetic ID)."""

import unittest
from datetime import datetime, timedelta
from engine.fraud_detector import FraudDetector
from generator.customer_generator import CustomerGenerator
from models.transaction import Transaction, TransactionType, TransactionDirection
from models.risk_score import AlertSeverity

class TestFraudDetector(unittest.TestCase):

    def setUp(self):
        self.detector = FraudDetector()
        self.cg = CustomerGenerator(seed=505)
        self.customer = self.cg.generate_customer("CUST-FR-TEST", archetype_name="DOMESTIC_SALARIED_LOW_RISK")

    def test_clean_customer_fraud_profile(self):
        alerts, pillar = self.detector.analyze_fraud(self.customer, [])
        self.assertEqual(len(alerts), 0)
        self.assertLess(pillar.raw_score, 20.0)

    def test_account_takeover_detection(self):
        now = datetime.now()
        # Legitimate login in home country
        tx1 = Transaction(
            transaction_id="TX-ATO-LEGIT",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(minutes=40)).isoformat(),
            transaction_type=TransactionType.POS_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=25.0,
            counterparty_name="Local Cafe",
            counterparty_country=self.customer.residence_country,
            counterparty_category="RETAILER",
            channel="POS_TERMINAL",
            reference_narrative="Coffee",
            device_id=self.customer.device_primary_id,
            ip_address=self.customer.primary_ip_address,
            ip_country=self.customer.primary_ip_country
        )
        # Hostile drain from foreign IP on unknown device 30 mins later
        tx2 = Transaction(
            transaction_id="TX-ATO-DRAIN",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=8500.0,
            counterparty_name="Offshore Crypto Ramp",
            counterparty_country="SC",
            counterparty_category="CRYPTO_EXCHANGE",
            channel="WEB_PORTAL",
            reference_narrative="External wire to unverified wallet",
            device_id="DEV-ATTACKER-UNKNOWN",
            ip_address="185.220.101.5",
            ip_country="RU"
        )

        alerts, pillar = self.detector.analyze_fraud(self.customer, [tx1, tx2])
        self.assertTrue(any(a.rule_id == "FR-01" for a in alerts))
        ato_alert = next(a for a in alerts if a.rule_id == "FR-01")
        self.assertEqual(ato_alert.severity, AlertSeverity.CRITICAL)
        self.assertGreaterEqual(pillar.raw_score, 85.0)

    def test_card_testing_detection(self):
        now = datetime.now()
        t1 = Transaction(
            transaction_id="TX-CARD-1",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(minutes=15)).isoformat(),
            transaction_type=TransactionType.ONLINE_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=0.89,
            counterparty_name="Micro Merchant A",
            counterparty_country="US",
            counterparty_category="RETAILER",
            channel="WEB_PORTAL",
            card_entry_mode="CNP_ECOMMERCE",
            reference_narrative="Test charge"
        )
        t2 = Transaction(
            transaction_id="TX-CARD-2",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(minutes=10)).isoformat(),
            transaction_type=TransactionType.ONLINE_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=1.20,
            counterparty_name="Micro Merchant B",
            counterparty_country="US",
            counterparty_category="RETAILER",
            channel="WEB_PORTAL",
            card_entry_mode="CNP_ECOMMERCE",
            reference_narrative="Test charge"
        )
        t3 = Transaction(
            transaction_id="TX-CARD-DRAIN",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.ONLINE_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=2800.0,
            counterparty_name="High-End Luxury Electronics",
            counterparty_country="HK",
            counterparty_category="RETAILER",
            channel="WEB_PORTAL",
            card_entry_mode="CNP_ECOMMERCE",
            auth_status="DECLINED_SUSPECTED_FRAUD",
            reference_narrative="Expedited luxury order"
        )

        alerts, pillar = self.detector.analyze_fraud(self.customer, [t1, t2, t3])
        self.assertTrue(any(a.rule_id == "FR-02" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 80.0)

    def test_app_scam_detection(self):
        now = datetime.now()
        tx = Transaction(
            transaction_id="TX-SCAM-1",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.P2P_TRANSFER_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=8500.0,
            counterparty_name="Alpha Yield Arbitrage Pool",
            counterparty_country="GB",
            counterparty_category="INDIVIDUAL",
            channel="MOBILE_APP",
            is_new_payee=True,
            payee_first_seen_hours=0.4,
            reference_narrative="Urgent guaranteed return investment enrollment fee"
        )

        alerts, pillar = self.detector.analyze_fraud(self.customer, [tx])
        self.assertTrue(any(a.rule_id == "FR-03" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 80.0)

    def test_bust_out_detection(self):
        now = datetime.now()
        inbound_dep = Transaction(
            transaction_id="TX-BUST-DEP",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(hours=12)).isoformat(),
            transaction_type=TransactionType.ACH_DEPOSIT,
            direction=TransactionDirection.INBOUND,
            amount_usd=9500.0,
            counterparty_name="External Account",
            counterparty_country="US",
            counterparty_category="INDIVIDUAL",
            channel="WEB_PORTAL",
            reference_narrative="ACH credit"
        )
        drain1 = Transaction(
            transaction_id="TX-BUST-OUT-1",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(hours=8)).isoformat(),
            transaction_type=TransactionType.ATM_WITHDRAWAL,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=1000.0,
            counterparty_name="ATM #101",
            counterparty_country="US",
            counterparty_category="ATM",
            channel="ATM",
            reference_narrative="ATM cash extraction"
        )
        drain2 = Transaction(
            transaction_id="TX-BUST-OUT-2",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(hours=2)).isoformat(),
            transaction_type=TransactionType.P2P_TRANSFER_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=7200.0,
            counterparty_name="Peer Transfer",
            counterparty_country="US",
            counterparty_category="PEER",
            channel="MOBILE_APP",
            reference_narrative="Urgent P2P drain"
        )

        alerts, pillar = self.detector.analyze_fraud(self.customer, [inbound_dep, drain1, drain2])
        self.assertTrue(any(a.rule_id == "FR-04" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 85.0)

    def test_synthetic_identity_detection(self):
        synth_customer = self.cg.generate_customer("CUST-SYNTH", archetype_name="SYNTHETIC_IDENTITY_FRAUD")
        alerts, pillar = self.detector.analyze_fraud(synth_customer, [])
        self.assertTrue(any(a.rule_id == "FR-05" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 75.0)

    def test_sim_swap_detection(self):
        now = datetime.now()
        tx = Transaction(
            transaction_id="TX-SIM-TEST",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.DOMESTIC_WIRE_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=8500.0,
            counterparty_name="NeoBank Digital Escrow LLC",
            counterparty_country=self.customer.residence_country,
            counterparty_category="OFFSHORE_CORP",
            channel="MOBILE_APP",
            reference_narrative="SIM Swap MFA reset detected: Urgent balance evacuation to external account",
            device_id="DEV-ROGUE-99",
            is_new_payee=True,
            is_fraud_synthetic=True,
            fraud_typology_tag="SIM_SWAP_DRAIN"
        )
        alerts, pillar = self.detector.analyze_fraud(self.customer, [tx])
        self.assertTrue(any(a.rule_id == "FR-06" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 85.0)

    def test_friendly_fraud_detection(self):
        now = datetime.now()
        tx1 = Transaction(
            transaction_id="TX-FF-1",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(days=5)).isoformat(),
            transaction_type=TransactionType.ONLINE_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=750.0,
            counterparty_name="Tech Store Direct",
            counterparty_country=self.customer.residence_country,
            counterparty_category="RETAILER",
            channel="WEB_PORTAL",
            reference_narrative="Dispute: Unauthorized transaction claim filed by cardholder",
            device_id=self.customer.device_primary_id,
            ip_country=self.customer.primary_ip_country,
            fraud_typology_tag="FRIENDLY_FRAUD_DISPUTE"
        )
        tx2 = Transaction(
            transaction_id="TX-FF-2",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.ONLINE_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=890.0,
            counterparty_name="Luxe Goods",
            counterparty_country=self.customer.residence_country,
            counterparty_category="RETAILER",
            channel="WEB_PORTAL",
            reference_narrative="Chargeback: Cardholder claims stolen identity",
            device_id=self.customer.device_primary_id,
            ip_country=self.customer.primary_ip_country,
            fraud_typology_tag="FRIENDLY_FRAUD_DISPUTE"
        )
        alerts, pillar = self.detector.analyze_fraud(self.customer, [tx1, tx2])
        self.assertTrue(any(a.rule_id == "FR-07" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 70.0)

    def test_bin_attack_detection(self):
        now = datetime.now()
        txs = []
        for i, status in enumerate(["DECLINED_INVALID_CVV", "DECLINED_EXPIRED", "DECLINED_SUSPECTED_FRAUD"]):
            txs.append(Transaction(
                transaction_id=f"TX-BIN-{i}",
                customer_id=self.customer.customer_id,
                timestamp=(now - timedelta(minutes=10 - i * 3)).isoformat(),
                transaction_type=TransactionType.ONLINE_PURCHASE,
                direction=TransactionDirection.OUTBOUND,
                amount_usd=1.99,
                counterparty_name="Global FastPay",
                counterparty_country="US",
                counterparty_category="RETAILER",
                channel="WEB_PORTAL",
                auth_status=status,
                reference_narrative="Botnet testing"
            ))
        alerts, pillar = self.detector.analyze_fraud(self.customer, txs)
        self.assertTrue(any(a.rule_id == "FR-08" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 80.0)

    def test_bec_detection(self):
        now = datetime.now()
        tx = Transaction(
            transaction_id="TX-BEC-1",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=55000.0,
            counterparty_name="Meridian Nominee Ltd",
            counterparty_country="HK",
            counterparty_category="OFFSHORE_CORP",
            channel="SWIFT",
            reference_narrative="Strictly Confidential M&A Acquisition Settlement Ref #9941 / CEO Authorization Required",
            is_new_payee=True,
            fraud_typology_tag="BEC_PAYROLL_IMPERSONATION"
        )
        alerts, pillar = self.detector.analyze_fraud(self.customer, [tx])
        self.assertTrue(any(a.rule_id == "FR-09" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 85.0)

    def test_aitm_detection(self):
        now = datetime.now()
        tx = Transaction(
            transaction_id="TX-AITM-1",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.DOMESTIC_WIRE_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=6200.0,
            counterparty_name="SwiftClear Virtual Settlement Hub",
            counterparty_country="US",
            counterparty_category="CRYPTO_EXCHANGE",
            channel="WEB_PORTAL",
            ip_country="DE",
            reference_narrative="Reverse proxy session token replay: Instant wire out to third-party clearing wallet",
            is_new_payee=True,
            fraud_typology_tag="PHISHING_AITM_SESSION_HIJACK"
        )
        alerts, pillar = self.detector.analyze_fraud(self.customer, [tx])
        self.assertTrue(any(a.rule_id == "FR-10" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 85.0)

    def test_overpayment_detection(self):
        now = datetime.now()
        t_in = Transaction(
            transaction_id="TX-OVP-IN",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(hours=14)).isoformat(),
            transaction_type=TransactionType.ACH_DEPOSIT,
            direction=TransactionDirection.INBOUND,
            amount_usd=16000.0,
            counterparty_name="National Corporate Disbursing Escrow",
            counterparty_country="US",
            counterparty_category="INDIVIDUAL",
            channel="WEB_PORTAL",
            reference_narrative="Corporate equipment advance check"
        )
        t_out = Transaction(
            transaction_id="TX-OVP-OUT",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.DOMESTIC_WIRE_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=12000.0,
            counterparty_name="Regional Courier Agent",
            counterparty_country="US",
            counterparty_category="INDIVIDUAL",
            channel="WEB_PORTAL",
            reference_narrative="Overpayment refund of unused advance to courier agent",
            is_new_payee=True,
            fraud_typology_tag="REFUND_OVERPAYMENT_SCAM"
        )
        alerts, pillar = self.detector.analyze_fraud(self.customer, [t_in, t_out])
        self.assertTrue(any(a.rule_id == "FR-11" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 80.0)

if __name__ == "__main__":
    unittest.main()
