"""Tests for Transaction Monitoring anomaly detectors and AML typologies."""

import unittest
from datetime import datetime, timedelta
from engine.tm_detector import TransactionMonitoringDetector
from generator.customer_generator import CustomerGenerator
from models.transaction import Transaction, TransactionType, TransactionDirection
from models.risk_score import AlertSeverity

class TestTMDetector(unittest.TestCase):

    def setUp(self):
        self.detector = TransactionMonitoringDetector()
        self.cg = CustomerGenerator(seed=303)
        self.customer = self.cg.generate_customer("CUST-TM-TEST", archetype_name="DOMESTIC_SALARIED_LOW_RISK")

    def test_structuring_detector(self):
        # Create 4 cash deposits just below $10,000 threshold within 10 days
        now = datetime.now()
        txs = []
        for i in range(4):
            txs.append(Transaction(
                transaction_id=f"TX-STRUC-{i}",
                customer_id=self.customer.customer_id,
                timestamp=(now - timedelta(days=i*2)).isoformat(),
                transaction_type=TransactionType.CASH_DEPOSIT,
                direction=TransactionDirection.INBOUND,
                amount_usd=9450.0,
                counterparty_name="Branch Teller #101",
                counterparty_country="US",
                counterparty_category="ATM_BRANCH",
                channel="BRANCH_TELLER",
                reference_narrative="Deposit"
            ))

        alerts, pillar = self.detector.analyze_transactions(self.customer, txs)
        self.assertTrue(any(a.rule_id == "TM-01" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 75.0)

    def test_money_mule_pass_through_detector(self):
        # Large inflow followed by rapid outbound dissipation (94% within 24h)
        now = datetime.now()
        inflow = Transaction(
            transaction_id="TX-MULE-IN",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(hours=30)).isoformat(),
            transaction_type=TransactionType.INTERNATIONAL_WIRE_IN,
            direction=TransactionDirection.INBOUND,
            amount_usd=28000.0,
            counterparty_name="Offshore Holding Corp",
            counterparty_country="AE",
            counterparty_category="OFFSHORE_CORP",
            channel="SWIFT",
            reference_narrative="Consulting fees"
        )
        outflow = Transaction(
            transaction_id="TX-MULE-OUT",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(hours=10)).isoformat(),
            transaction_type=TransactionType.CRYPTO_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=26500.0, # 94.6% drain
            counterparty_name="Binance P2P",
            counterparty_country="SC",
            counterparty_category="CRYPTO_EXCHANGE",
            channel="WEB_PORTAL",
            reference_narrative="Crypto buy"
        )

        alerts, pillar = self.detector.analyze_transactions(self.customer, [inflow, outflow])
        self.assertTrue(any(a.rule_id == "TM-02" for a in alerts))
        mule_alert = next(a for a in alerts if a.rule_id == "TM-02")
        self.assertEqual(mule_alert.severity, AlertSeverity.CRITICAL)

    def test_turnover_profile_deviation(self):
        # Customer expects $5,000/mo, but transacts $45,000 in 30 days
        self.customer.declared_expected_monthly_turnover_usd = 5000.0
        now = datetime.now()
        txs = []
        for i in range(5):
            txs.append(Transaction(
                transaction_id=f"TX-DEV-{i}",
                customer_id=self.customer.customer_id,
                timestamp=(now - timedelta(days=i*5)).isoformat(),
                transaction_type=TransactionType.ACH_DEPOSIT,
                direction=TransactionDirection.INBOUND,
                amount_usd=9000.0, # Total $45,000 = 9x declared!
                counterparty_name="Client Corp",
                counterparty_country="US",
                counterparty_category="RETAILER",
                channel="ACH",
                reference_narrative="Settlement"
            ))

        alerts, pillar = self.detector.analyze_transactions(self.customer, txs)
        self.assertTrue(any(a.rule_id == "TM-03" for a in alerts))

    def test_fatf_blacklist_corridor(self):
        # Wire to Iran (IR) or North Korea (KP)
        now = datetime.now()
        bl_tx = Transaction(
            transaction_id="TX-BL-01",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=35000.0,
            counterparty_name="Tehran Commercial Lines",
            counterparty_country="IR",
            counterparty_category="OFFSHORE_CORP",
            channel="SWIFT",
            reference_narrative="Import cargo release"
        )

        alerts, pillar = self.detector.analyze_transactions(self.customer, [bl_tx])
        self.assertTrue(any(a.rule_id == "TM-05A" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 90.0)

    def test_dormancy_break_surge(self):
        # 75 days gap followed by $18,000 wire
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        t1 = t0 + timedelta(days=75)
        tx1 = Transaction(
            transaction_id="TX-DORM-1",
            customer_id=self.customer.customer_id,
            timestamp=t0.isoformat(),
            transaction_type=TransactionType.POS_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=50.0,
            counterparty_name="Grocery",
            counterparty_country="US",
            counterparty_category="RETAILER",
            channel="POS_TERMINAL",
            reference_narrative="Groceries"
        )
        tx2 = Transaction(
            transaction_id="TX-DORM-2",
            customer_id=self.customer.customer_id,
            timestamp=t1.isoformat(),
            transaction_type=TransactionType.DOMESTIC_WIRE_IN,
            direction=TransactionDirection.INBOUND,
            amount_usd=25000.0,
            counterparty_name="Unknown Trust Account",
            counterparty_country="US",
            counterparty_category="INDIVIDUAL",
            channel="WEB_PORTAL",
            reference_narrative="Funds transfer"
        )

        alerts, pillar = self.detector.analyze_transactions(self.customer, [tx1, tx2])
        self.assertTrue(any(a.rule_id == "TM-06" for a in alerts))

    def test_tbml_detection(self):
        now = datetime.now()
        tx1 = Transaction(
            transaction_id="TX-TBML-1",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(days=2)).isoformat(),
            transaction_type=TransactionType.INTERNATIONAL_WIRE_IN,
            direction=TransactionDirection.INBOUND,
            amount_usd=65000.0,
            counterparty_name="Al-Noor Petrochem & General Trading LLC",
            counterparty_country="AE",
            counterparty_category="OFFSHORE_CORP",
            channel="SWIFT",
            reference_narrative="Consignment commercial invoice #4902 - raw industrial polymers cargo",
            synthetic_typology_tag="TBML_OVER_INVOICING"
        )
        tx2 = Transaction(
            transaction_id="TX-TBML-2",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=58000.0,
            counterparty_name="Star Ocean Shipping Logistics Ltd",
            counterparty_country="HK",
            counterparty_category="OFFSHORE_CORP",
            channel="SWIFT",
            reference_narrative="Bill of Lading #BOL-9912 - bulk freight customs & transshipment fee",
            synthetic_typology_tag="TBML_OVER_INVOICING"
        )
        alerts, pillar = self.detector.analyze_transactions(self.customer, [tx1, tx2])
        self.assertTrue(any(a.rule_id == "TM-08" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 80.0)

    def test_fan_out_layering_detection(self):
        now = datetime.now()
        t_in = Transaction(
            transaction_id="TX-FAN-IN",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(hours=18)).isoformat(),
            transaction_type=TransactionType.DOMESTIC_WIRE_IN,
            direction=TransactionDirection.INBOUND,
            amount_usd=35000.0,
            counterparty_name="Vanguard Escrow Holdings Trust",
            counterparty_country="US",
            counterparty_category="OFFSHORE_CORP",
            channel="WEB_PORTAL",
            reference_narrative="Private contract disbursement proceeds",
            synthetic_typology_tag="FAN_OUT_LAYERING"
        )
        out_txs = [t_in]
        for i in range(4):
            out_txs.append(Transaction(
                transaction_id=f"TX-FAN-OUT-{i}",
                customer_id=self.customer.customer_id,
                timestamp=(now - timedelta(hours=12 - i * 3)).isoformat(),
                transaction_type=TransactionType.P2P_TRANSFER_OUT,
                direction=TransactionDirection.OUTBOUND,
                amount_usd=7000.0,
                counterparty_name=f"Peer Beneficiary {i}",
                counterparty_country="US",
                counterparty_category="PEER",
                channel="MOBILE_APP",
                reference_narrative=f"Fan-out distribution leg #{i+1}",
                synthetic_typology_tag="FAN_OUT_LAYERING"
            ))
        alerts, pillar = self.detector.analyze_transactions(self.customer, out_txs)
        self.assertTrue(any(a.rule_id == "TM-09" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 80.0)

    def test_cuckoo_smurfing_detection(self):
        now = datetime.now()
        txs = []
        for i in range(3):
            txs.append(Transaction(
                transaction_id=f"TX-CUCK-{i}",
                customer_id=self.customer.customer_id,
                timestamp=(now - timedelta(days=i * 2)).isoformat(),
                transaction_type=TransactionType.CASH_DEPOSIT,
                direction=TransactionDirection.INBOUND,
                amount_usd=4500.0,
                counterparty_name=f"Branch Cash Counter #{i+10}",
                counterparty_country="US",
                counterparty_category="ATM_BRANCH",
                channel="BRANCH_TELLER",
                reference_narrative="Hawala third-party remittance aggregation deposit",
                synthetic_typology_tag="CUCKOO_SMURFING"
            ))
        alerts, pillar = self.detector.analyze_transactions(self.customer, txs)
        self.assertTrue(any(a.rule_id == "TM-10" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 80.0)

    def test_crypto_mixer_detection(self):
        now = datetime.now()
        tx = Transaction(
            transaction_id="TX-MIX-1",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.CRYPTO_PURCHASE,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=15000.0,
            counterparty_name="Tornado Cash Router 0xd90e... (Sanctioned Protocol)",
            counterparty_country="SC",
            counterparty_category="CRYPTO_MIXER",
            channel="WEB_PORTAL",
            reference_narrative="Direct deposit to zero-knowledge privacy pool / mixer contract",
            synthetic_typology_tag="CRYPTO_MIXER_HOP"
        )
        alerts, pillar = self.detector.analyze_transactions(self.customer, [tx])
        self.assertTrue(any(a.rule_id == "TM-11" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 90.0)

    def test_human_trafficking_detection(self):
        now = datetime.now()
        txs = []
        for i in range(3):
            txs.append(Transaction(
                transaction_id=f"TX-HT-IN-{i}",
                customer_id=self.customer.customer_id,
                timestamp=(now - timedelta(hours=i * 2 + 6)).isoformat(),
                transaction_type=TransactionType.P2P_TRANSFER_IN,
                direction=TransactionDirection.INBOUND,
                amount_usd=800.0,
                counterparty_name=f"Worker Wage {i}",
                counterparty_country="US",
                counterparty_category="PEER",
                channel="MOBILE_APP",
                reference_narrative="Worker wage deduction for recruitment fee / centralized payroll skimming",
                synthetic_typology_tag="HUMAN_TRAFFICKING_RED_FLAGS"
            ))
        alerts, pillar = self.detector.analyze_transactions(self.customer, txs)
        self.assertTrue(any(a.rule_id == "TM-12" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 90.0)

    def test_loan_wash_detection(self):
        now = datetime.now()
        t_in = Transaction(
            transaction_id="TX-LOAN-IN",
            customer_id=self.customer.customer_id,
            timestamp=(now - timedelta(days=12)).isoformat(),
            transaction_type=TransactionType.DOMESTIC_WIRE_IN,
            direction=TransactionDirection.INBOUND,
            amount_usd=35000.0,
            counterparty_name="Valiant Commercial Credit Disbursal Unit",
            counterparty_country="US",
            counterparty_category="OFFSHORE_CORP",
            channel="SWIFT",
            reference_narrative="Term loan disbursement principal funding",
            synthetic_typology_tag="LOAN_COLLATERAL_WASH"
        )
        t_out = Transaction(
            transaction_id="TX-LOAN-OUT",
            customer_id=self.customer.customer_id,
            timestamp=now.isoformat(),
            transaction_type=TransactionType.INTERNATIONAL_WIRE_OUT,
            direction=TransactionDirection.OUTBOUND,
            amount_usd=35100.0,
            counterparty_name="Valiant Credit Loan Servicing Dept",
            counterparty_country="US",
            counterparty_category="OFFSHORE_CORP",
            channel="SWIFT",
            reference_narrative="Loan settlement full: Early payoff using offshore liquidity release",
            synthetic_typology_tag="LOAN_COLLATERAL_WASH"
        )
        alerts, pillar = self.detector.analyze_transactions(self.customer, [t_in, t_out])
        self.assertTrue(any(a.rule_id == "TM-13" for a in alerts))
        self.assertGreaterEqual(pillar.raw_score, 75.0)

if __name__ == "__main__":
    unittest.main()
