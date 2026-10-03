"""Fraud detection engine: analyzes digital identity, device telemetry, card patterns, and fraud typologies."""

from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
from models.customer import CustomerProfile
from models.transaction import Transaction, TransactionDirection, TransactionType
from models.risk_score import FraudAlert, AlertSeverity, PillarScore
from config.fraud_config import FRAUD_RULES_CONFIG, FRAML_PILLAR_WEIGHTS

class FraudDetector:
    """Detects First-Party and Third-Party Fraud typologies across retail banking profiles."""

    def __init__(self, config: Dict[str, Any] = FRAUD_RULES_CONFIG):
        self.config = config

    def analyze_fraud(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> Tuple[List[FraudAlert], PillarScore]:
        """
        Runs fraud detection rules over customer profile and transaction history.
        Returns: (List of FraudAlerts, PillarScore)
        """
        alerts: List[FraudAlert] = []
        tx_sorted = sorted(transactions, key=lambda t: t.timestamp) if transactions else []

        # 1. Profile-Level Fraud: Synthetic Identity & Burner Footprint
        alerts.extend(self._detect_synthetic_identity(customer))

        # 2. Transactional Fraud Rules
        if tx_sorted:
            alerts.extend(self._detect_account_takeover(customer, tx_sorted))
            alerts.extend(self._detect_card_testing(customer, tx_sorted))
            alerts.extend(self._detect_app_scam(customer, tx_sorted))
            alerts.extend(self._detect_bust_out_fraud(customer, tx_sorted))

        # 3. Calculate Fraud Pillar Score
        if not alerts and customer.synthetic_identity_score < 30.0:
            raw_score = max(5.0, customer.synthetic_identity_score * 0.5)
            factors = [
                "Digital identity verification validated (clean carrier & domain)",
                "No unauthorized device logins or card velocity anomalies",
                "Transaction auth status clean with trusted device fingerprints"
            ]
        else:
            score_impacts = [a.score_impact for a in alerts]
            if customer.synthetic_identity_score >= self.config["SYNTHETIC_ID_SCORE_THRESHOLD"]:
                score_impacts.append(customer.synthetic_identity_score)

            score_impacts.sort(reverse=True)
            raw_score = score_impacts[0] if score_impacts else 10.0
            if len(score_impacts) > 1:
                raw_score += sum(score_impacts[1:]) * 0.25
            raw_score = min(100.0, max(0.0, raw_score))

            factors = [
                f"Triggered {len(alerts)} Fraud detection alert(s):",
                *[f"- [{a.severity.value}] {a.rule_name}: {a.summary}" for a in alerts]
            ]
            if customer.synthetic_id_indicators:
                factors.extend([f"- [SYNTHETIC ID RISK]: {ind}" for ind in customer.synthetic_id_indicators])

        weight = FRAML_PILLAR_WEIGHTS["FRAUD_RISK"]
        pillar_score = PillarScore(
            pillar_name="Fraud Risk & Digital Footprint",
            weight=weight,
            raw_score=round(raw_score, 2),
            weighted_score=round(raw_score * weight, 2),
            contributing_factors=factors
        )

        return alerts, pillar_score

    def _detect_synthetic_identity(self, customer: CustomerProfile) -> List[FraudAlert]:
        """Detects Synthetic Identity Fraud, disposable burner emails, and VoIP lines."""
        alerts = []
        is_burner_email = customer.email_domain_type == "DISPOSABLE_TEMP"
        is_voip = customer.phone_line_type == "VOIP_VIRTUAL"
        high_synth_score = customer.synthetic_identity_score >= self.config["SYNTHETIC_ID_SCORE_THRESHOLD"]

        if is_burner_email or is_voip or high_synth_score:
            severity = AlertSeverity.CRITICAL if (is_burner_email and is_voip) else AlertSeverity.HIGH
            alerts.append(FraudAlert(
                alert_id=f"FR-ALT-SYNTH-{customer.customer_id}",
                rule_id="FR-05",
                rule_name="Synthetic Identity & Burner Contact Screening",
                severity=severity,
                score_impact=85.0 if severity == AlertSeverity.CRITICAL else 70.0,
                summary=(
                    f"Applicant registered with disposable email domain ({customer.email_address}) "
                    f"and virtual VoIP number ({customer.phone_number}). "
                    f"Synthetic identity algorithm index: {customer.synthetic_identity_score:.1f}/100."
                ),
                trigger_details={
                    "synthetic_identity_score": customer.synthetic_identity_score,
                    "email_domain_type": customer.email_domain_type,
                    "phone_line_type": customer.phone_line_type,
                    "indicators": customer.synthetic_id_indicators
                },
                supporting_transaction_ids=[]
            ))

        return alerts

    def _detect_account_takeover(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects Account Takeover (ATO): Outbound drain from foreign IP / unauthorized device."""
        alerts = []
        primary_dev = customer.device_primary_id
        primary_country = customer.primary_ip_country or customer.residence_country

        for i, tx in enumerate(transactions):
            if tx.direction != TransactionDirection.OUTBOUND:
                continue

            # ATO typically manifests through online banking transfers, wires, P2P, or crypto offramps
            if tx.transaction_type not in [
                TransactionType.INTERNATIONAL_WIRE_OUT,
                TransactionType.DOMESTIC_WIRE_OUT,
                TransactionType.P2P_TRANSFER_OUT,
                TransactionType.CRYPTO_PURCHASE,
                TransactionType.ACH_WITHDRAWAL
            ]:
                continue

            is_foreign_ip = tx.ip_country and tx.ip_country != primary_country
            is_unrecognized_dev = tx.device_id and tx.device_id != primary_dev
            is_significant_drain = tx.amount_usd >= self.config["ATO_MIN_DRAIN_AMOUNT_USD"]

            # Check if preceded by a legitimate session in home country shortly before (impossible travel)
            if is_foreign_ip and is_unrecognized_dev and is_significant_drain:
                # Look back at preceding legitimate transactions
                t_curr = datetime.fromisoformat(tx.timestamp)
                prev_legit = [
                    t for t in transactions[:i]
                    if t.ip_country == primary_country
                    and (t_curr - datetime.fromisoformat(t.timestamp)).total_seconds() <= (self.config["ATO_TIME_WINDOW_MINUTES"] * 60)
                ]

                window_mins = self.config["ATO_TIME_WINDOW_MINUTES"]
                alerts.append(FraudAlert(
                    alert_id=f"FR-ALT-ATO-{tx.transaction_id}",
                    rule_id="FR-01",
                    rule_name="Account Takeover (ATO) & Impossible Travel Anomaly",
                    severity=AlertSeverity.CRITICAL,
                    score_impact=self.config["ATO_RISK_SCORE"],
                    summary=(
                        f"Outbound transfer of ${tx.amount_usd:,.2f} executed from anomalous device '{tx.device_id}' "
                        f"and foreign IP {tx.ip_address} ({tx.ip_country}) shortly after session in {primary_country}. "
                        f"Pattern indicates compromised online banking credentials."
                    ),
                    trigger_details={
                        "draining_transaction_id": tx.transaction_id,
                        "amount_usd": tx.amount_usd,
                        "hostile_device_id": tx.device_id,
                        "hostile_ip": tx.ip_address,
                        "hostile_ip_country": tx.ip_country,
                        "registered_home_country": primary_country,
                        "registered_device": primary_dev,
                        "counterparty": tx.counterparty_name
                    },
                    supporting_transaction_ids=[tx.transaction_id] + [p.transaction_id for p in prev_legit]
                ))
                break

        return alerts

    def _detect_card_testing(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects Card Testing / Micro-probing followed by High-Value CNP Drain."""
        alerts = []
        max_micro = self.config["CARD_TEST_MICRO_MAX_USD"]
        drain_min = self.config["CARD_TEST_DRAIN_MIN_USD"]
        window_mins = self.config["CARD_TEST_WINDOW_MINUTES"]

        card_txs = [
            t for t in transactions
            if t.card_entry_mode == "CNP_ECOMMERCE" or t.channel in ["WEB_PORTAL", "POS_TERMINAL"]
        ]

        for i, t in enumerate(card_txs):
            if t.amount_usd <= max_micro and t.direction == TransactionDirection.OUTBOUND:
                t_time = datetime.fromisoformat(t.timestamp)
                max_window = t_time + timedelta(minutes=window_mins)

                # Look for subsequent micro-tests or immediate drain
                cluster = [t]
                drain_tx = None
                for j in range(i + 1, len(card_txs)):
                    t_next = card_txs[j]
                    t_next_time = datetime.fromisoformat(t_next.timestamp)
                    if t_next_time > max_window:
                        break
                    if t_next.amount_usd <= max_micro:
                        cluster.append(t_next)
                    elif t_next.amount_usd >= drain_min:
                        drain_tx = t_next
                        break

                if len(cluster) >= self.config["CARD_TEST_MIN_PROBES"] and drain_tx:
                    supporting_ids = [c.transaction_id for c in cluster] + [drain_tx.transaction_id]
                    alerts.append(FraudAlert(
                        alert_id=f"FR-ALT-CARD-{t.transaction_id}",
                        rule_id="FR-02",
                        rule_name="Card Testing / Micro-Authorization Probing Attack",
                        severity=AlertSeverity.HIGH if drain_tx.auth_status == "DECLINED_SUSPECTED_FRAUD" else AlertSeverity.CRITICAL,
                        score_impact=self.config["CARD_TEST_RISK_SCORE"],
                        summary=(
                            f"Detected {len(cluster)} micro-authorization card probes (avg ${sum(c.amount_usd for c in cluster)/len(cluster):.2f}) "
                            f"immediately followed within {window_mins} mins by ${drain_tx.amount_usd:,.2f} high-dollar CNP purchase attempt "
                            f"at '{drain_tx.counterparty_name}' (Status: {drain_tx.auth_status})."
                        ),
                        trigger_details={
                            "micro_probes_count": len(cluster),
                            "probe_amounts": [c.amount_usd for c in cluster],
                            "drain_amount_usd": drain_tx.amount_usd,
                            "drain_auth_status": drain_tx.auth_status,
                            "drain_counterparty": drain_tx.counterparty_name
                        },
                        supporting_transaction_ids=supporting_ids
                    ))
                    break

        return alerts

    def _detect_app_scam(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects Authorized Push Payment (APP) / Investment & Romance Scams."""
        alerts = []
        min_outflow = self.config["APP_SCAM_MIN_OUTFLOW_USD"]

        scam_keywords = ["guaranteed", "arbitrage", "investment enrollment", "release", "bail", "tax clearance", "profit"]

        scam_txs = []
        for t in transactions:
            if t.direction == TransactionDirection.OUTBOUND and t.is_new_payee and t.amount_usd >= min_outflow:
                narrative_lower = t.reference_narrative.lower()
                if any(kw in narrative_lower for kw in scam_keywords):
                    scam_txs.append(t)

        if scam_txs:
            total_scam_usd = sum(t.amount_usd for t in scam_txs)
            alerts.append(FraudAlert(
                alert_id=f"FR-ALT-SCAM-{customer.customer_id}",
                rule_id="FR-03",
                rule_name="Authorized Push Payment (APP) / Investment & Impersonation Scam",
                severity=AlertSeverity.HIGH,
                score_impact=self.config["APP_SCAM_RISK_SCORE"],
                summary=(
                    f"Customer initiated {len(scam_txs)} rapid transfers totaling ${total_scam_usd:,.2f} "
                    f"to brand new unverified payees ({', '.join(t.counterparty_name for t in scam_txs)}) "
                    f"with high-risk investment/scam narratives. Strong indicator of customer manipulation/coercion."
                ),
                trigger_details={
                    "count": len(scam_txs),
                    "total_scam_usd": total_scam_usd,
                    "counterparties": [t.counterparty_name for t in scam_txs],
                    "narratives": [t.reference_narrative for t in scam_txs]
                },
                supporting_transaction_ids=[t.transaction_id for t in scam_txs]
            ))

        return alerts

    def _detect_bust_out_fraud(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects First-Party Bust-Out / Deposit Kiting Fraud."""
        alerts = []
        min_dep = self.config["BUSTOUT_MIN_DEPOSIT_USD"]
        window_hours = self.config["BUSTOUT_TIME_WINDOW_HOURS"]
        ratio_trigger = self.config["BUSTOUT_WITHDRAWAL_RATIO"]

        ach_deposits = [
            t for t in transactions
            if t.direction == TransactionDirection.INBOUND
            and t.transaction_type == TransactionType.ACH_DEPOSIT
            and t.amount_usd >= min_dep
        ]

        for dep in ach_deposits:
            t_dep = datetime.fromisoformat(dep.timestamp)
            max_out_time = t_dep + timedelta(hours=window_hours)

            # Look for subsequent rapid ATM/cash/P2P drains
            drains = [
                t for t in transactions
                if t.direction == TransactionDirection.OUTBOUND
                and t.transaction_type in [TransactionType.ATM_WITHDRAWAL, TransactionType.P2P_TRANSFER_OUT, TransactionType.CASH_WITHDRAWAL]
                and t_dep <= datetime.fromisoformat(t.timestamp) <= max_out_time
            ]

            total_drain = sum(t.amount_usd for t in drains)
            if dep.amount_usd > 0 and (total_drain / dep.amount_usd) >= ratio_trigger:
                drain_ratio = total_drain / dep.amount_usd
                supporting_ids = [dep.transaction_id] + [t.transaction_id for t in drains]
                alerts.append(FraudAlert(
                    alert_id=f"FR-ALT-BUST-{dep.transaction_id}",
                    rule_id="FR-04",
                    rule_name="First-Party Bust-Out / Deposit Kiting Fraud",
                    severity=AlertSeverity.CRITICAL,
                    score_impact=self.config["BUSTOUT_RISK_SCORE"],
                    summary=(
                        f"Inbound unverified deposit of ${dep.amount_usd:,.2f} immediately drained "
                        f"({drain_ratio * 100:.1f}%) within {window_hours} hours via {len(drains)} rapid ATM/P2P cash extractions "
                        f"prior to fund settlement."
                    ),
                    trigger_details={
                        "deposit_id": dep.transaction_id,
                        "deposit_usd": dep.amount_usd,
                        "total_drain_usd": total_drain,
                        "drain_percentage": round(drain_ratio * 100, 1),
                        "drains_count": len(drains)
                    },
                    supporting_transaction_ids=supporting_ids
                ))
                break

        return alerts
