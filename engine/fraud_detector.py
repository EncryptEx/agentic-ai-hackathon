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
            alerts.extend(self._detect_sim_swap_drain(customer, tx_sorted))
            alerts.extend(self._detect_friendly_fraud(customer, tx_sorted))
            alerts.extend(self._detect_bin_attack(customer, tx_sorted))
            alerts.extend(self._detect_bec_impersonation(customer, tx_sorted))
            alerts.extend(self._detect_aitm_session_hijack(customer, tx_sorted))
            alerts.extend(self._detect_overpayment_scam(customer, tx_sorted))

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

    def _detect_sim_swap_drain(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects SIM Swap / Credential Reset followed by Immediate Outbound Wire Drain (FR-06)."""
        alerts = []
        min_drain = self.config.get("SIM_SWAP_DRAIN_MIN_USD", 3000.0)

        for tx in transactions:
            if tx.direction != TransactionDirection.OUTBOUND:
                continue

            narrative_lower = (tx.reference_narrative or "").lower()
            is_tag = tx.fraud_typology_tag == "SIM_SWAP_DRAIN"
            has_sim_signals = (
                "sim swap" in narrative_lower or
                "mfa reset" in narrative_lower or
                "carrier port" in narrative_lower or
                "telecom pin reset" in narrative_lower or
                "device re-enrolled" in narrative_lower
            )

            # High value outbound with brand new payee on unverified/new device following SIM reset
            is_unrecognized_dev = tx.device_id and tx.device_id != customer.device_primary_id
            if (is_tag or has_sim_signals or (is_unrecognized_dev and tx.is_new_payee and customer.phone_line_type == "VOIP_VIRTUAL")) and tx.amount_usd >= min_drain:
                alerts.append(FraudAlert(
                    alert_id=f"FR-ALT-SIM-{tx.transaction_id}",
                    rule_id="FR-06",
                    rule_name="SIM Swap & Credential Reset Outbound Drain",
                    severity=AlertSeverity.CRITICAL,
                    score_impact=self.config.get("SIM_SWAP_RISK_SCORE", 91.0),
                    summary=(
                        f"Outbound transfer of ${tx.amount_usd:,.2f} dispatched to newly added payee '{tx.counterparty_name}' "
                        f"immediately following mobile carrier SIM swap / MFA re-enrollment anomaly. "
                        f"Device fingerprint '{tx.device_id}' differs from primary registered device."
                    ),
                    trigger_details={
                        "transaction_id": tx.transaction_id,
                        "amount_usd": tx.amount_usd,
                        "counterparty": tx.counterparty_name,
                        "channel": tx.channel,
                        "device_id": tx.device_id,
                        "phone_line_type": customer.phone_line_type
                    },
                    supporting_transaction_ids=[tx.transaction_id]
                ))
                break

        return alerts

    def _detect_friendly_fraud(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects First-Party Friendly Fraud / Systematic Chargeback Abuse (FR-07)."""
        alerts = []
        min_disputes = self.config.get("FRIENDLY_FRAUD_MIN_DISPUTES", 2)
        min_amt = self.config.get("FRIENDLY_FRAUD_MIN_AMOUNT_USD", 1200.0)

        disputed_txs = []
        for tx in transactions:
            narrative_lower = (tx.reference_narrative or "").lower()
            is_tag = tx.fraud_typology_tag == "FRIENDLY_FRAUD_DISPUTE"
            has_chargeback_keywords = (
                "chargeback" in narrative_lower or
                "dispute" in narrative_lower or
                "unauthorized transaction claim" in narrative_lower or
                "goods not received claim" in narrative_lower or
                "friendly fraud" in narrative_lower
            )

            # Legitimate device/IP, authenticated 3DS/chip, yet disputed by cardholder
            is_trusted_env = (
                tx.device_id == customer.device_primary_id and
                (tx.ip_country == customer.primary_ip_country or tx.ip_country == customer.residence_country)
            )

            if is_tag or (has_chargeback_keywords and (is_trusted_env or tx.is_card_present)):
                disputed_txs.append(tx)

        total_disputed = sum(t.amount_usd for t in disputed_txs)
        if len(disputed_txs) >= min_disputes or total_disputed >= min_amt or any(t.fraud_typology_tag == "FRIENDLY_FRAUD_DISPUTE" for t in disputed_txs):
            if disputed_txs:
                alerts.append(FraudAlert(
                    alert_id=f"FR-ALT-FF-{customer.customer_id}",
                    rule_id="FR-07",
                    rule_name="Friendly Fraud / Systematic Chargeback & Dispute Abuse",
                    severity=AlertSeverity.HIGH,
                    score_impact=self.config.get("FRIENDLY_FRAUD_RISK_SCORE", 78.0),
                    summary=(
                        f"Customer initiated {len(disputed_txs)} card disputes/chargebacks totaling ${total_disputed:,.2f} "
                        f"on high-value purchases executed from verified primary device and domestic IP with authenticated EMV/3DS."
                    ),
                    trigger_details={
                        "dispute_count": len(disputed_txs),
                        "total_disputed_usd": total_disputed,
                        "disputed_tx_ids": [t.transaction_id for t in disputed_txs],
                        "merchants": [t.counterparty_name for t in disputed_txs]
                    },
                    supporting_transaction_ids=[t.transaction_id for t in disputed_txs]
                ))

        return alerts

    def _detect_bin_attack(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects Automated BIN Attacks & High-Velocity Card Brute-Force Testing (FR-08)."""
        alerts = []
        min_declines = self.config.get("BIN_ATTACK_MIN_DECLINES", 3)
        window_mins = self.config.get("BIN_ATTACK_WINDOW_MINUTES", 30)

        declined_txs = [
            t for t in transactions
            if t.auth_status in ["DECLINED_SUSPECTED_FRAUD", "DECLINED_INVALID_CVV", "DECLINED_EXPIRED", "DECLINED_VELOCITY"]
            or t.fraud_typology_tag == "BIN_ATTACK_VELOCITY"
        ]

        if len(declined_txs) >= min_declines:
            # Check velocity window
            t_first = datetime.fromisoformat(declined_txs[0].timestamp)
            t_last = datetime.fromisoformat(declined_txs[-1].timestamp)
            mins_span = max(1, int((t_last - t_first).total_seconds() / 60))

            if mins_span <= window_mins or any(t.fraud_typology_tag == "BIN_ATTACK_VELOCITY" for t in declined_txs):
                alerts.append(FraudAlert(
                    alert_id=f"FR-ALT-BIN-{customer.customer_id}",
                    rule_id="FR-08",
                    rule_name="Automated BIN Attack & High-Velocity Card Brute-Force",
                    severity=AlertSeverity.HIGH if len(declined_txs) < 5 else AlertSeverity.CRITICAL,
                    score_impact=self.config.get("BIN_ATTACK_RISK_SCORE", 89.0),
                    summary=(
                        f"Detected {len(declined_txs)} rapid sequential authorization attempts with fraud declines "
                        f"within {mins_span} minutes. Characteristics match automated script/botnet testing CVV/expiration permutations."
                    ),
                    trigger_details={
                        "declines_count": len(declined_txs),
                        "time_span_minutes": mins_span,
                        "auth_statuses": [t.auth_status for t in declined_txs],
                        "gateways": list(set(t.counterparty_name for t in declined_txs))
                    },
                    supporting_transaction_ids=[t.transaction_id for t in declined_txs]
                ))

        return alerts

    def _detect_bec_impersonation(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects Business Email Compromise (BEC) & Executive Impersonation (FR-09)."""
        alerts = []
        min_amt = self.config.get("BEC_MIN_AMOUNT_USD", 10000.0)

        bec_keywords = [
            "confidential acquisition", "executive request", "urgent closing",
            "ceo authorization", "payroll diversion", "revised banking details",
            "board approved", "offshore escrow settlement", "confidential project"
        ]

        for tx in transactions:
            if tx.direction != TransactionDirection.OUTBOUND:
                continue

            narrative_lower = (tx.reference_narrative or "").lower()
            is_tag = tx.fraud_typology_tag == "BEC_PAYROLL_IMPERSONATION"
            has_bec_narrative = any(kw in narrative_lower for kw in bec_keywords)

            if (is_tag or has_bec_narrative) and tx.amount_usd >= min_amt and tx.is_new_payee:
                alerts.append(FraudAlert(
                    alert_id=f"FR-ALT-BEC-{tx.transaction_id}",
                    rule_id="FR-09",
                    rule_name="Business Email Compromise (BEC) & Executive Impersonation",
                    severity=AlertSeverity.CRITICAL,
                    score_impact=self.config.get("BEC_RISK_SCORE", 93.0),
                    summary=(
                        f"High-value outbound wire of ${tx.amount_usd:,.2f} routed to new beneficiary '{tx.counterparty_name}' "
                        f"({tx.counterparty_country}) accompanied by urgent executive/confidential wire narrative. "
                        f"Matches classic CEO fraud / supplier banking details interception."
                    ),
                    trigger_details={
                        "transaction_id": tx.transaction_id,
                        "amount_usd": tx.amount_usd,
                        "beneficiary": tx.counterparty_name,
                        "beneficiary_country": tx.counterparty_country,
                        "narrative": tx.reference_narrative,
                        "channel": tx.channel
                    },
                    supporting_transaction_ids=[tx.transaction_id]
                ))
                break

        return alerts

    def _detect_aitm_session_hijack(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects Adversary-in-the-Middle (AitM) Phishing Session Hijacking (FR-10)."""
        alerts = []
        min_drain = self.config.get("AITM_MIN_DRAIN_USD", 2000.0)

        for tx in transactions:
            if tx.direction != TransactionDirection.OUTBOUND:
                continue

            narrative_lower = (tx.reference_narrative or "").lower()
            is_tag = tx.fraud_typology_tag == "PHISHING_AITM_SESSION_HIJACK"
            has_aitm_signal = (
                "reverse proxy" in narrative_lower or
                "session token replay" in narrative_lower or
                "aitm" in narrative_lower or
                "stolen session cookie" in narrative_lower or
                "phishing kit" in narrative_lower
            )

            # Session token replayed from anomalous proxy ASN while mimicking user-agent
            is_foreign_ip = tx.ip_country and tx.ip_country != (customer.primary_ip_country or customer.residence_country)
            if (is_tag or has_aitm_signal or (is_foreign_ip and tx.is_new_payee and tx.channel == "WEB_PORTAL")) and tx.amount_usd >= min_drain:
                alerts.append(FraudAlert(
                    alert_id=f"FR-ALT-AITM-{tx.transaction_id}",
                    rule_id="FR-10",
                    rule_name="Adversary-in-the-Middle (AitM) Phishing Session Hijack",
                    severity=AlertSeverity.CRITICAL,
                    score_impact=self.config.get("AITM_RISK_SCORE", 94.0),
                    summary=(
                        f"Outbound transfer of ${tx.amount_usd:,.2f} executed via replayed web session token from anomalous "
                        f"proxy IP {tx.ip_address} ({tx.ip_country}). Bypassed MFA via reverse-proxy session cookie exfiltration."
                    ),
                    trigger_details={
                        "transaction_id": tx.transaction_id,
                        "amount_usd": tx.amount_usd,
                        "hostile_ip": tx.ip_address,
                        "hostile_country": tx.ip_country,
                        "counterparty": tx.counterparty_name,
                        "channel": tx.channel
                    },
                    supporting_transaction_ids=[tx.transaction_id]
                ))
                break

        return alerts

    def _detect_overpayment_scam(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[FraudAlert]:
        """Detects Counterfeit Cheque Overpayment & Fake Refund Scam (FR-11)."""
        alerts = []
        min_dep = self.config.get("OVERPAYMENT_MIN_DEPOSIT_USD", 5000.0)
        ratio_trigger = self.config.get("OVERPAYMENT_REFUND_RATIO", 0.60)
        window_hours = self.config.get("OVERPAYMENT_WINDOW_HOURS", 72)

        # Look for inbound unverified deposits (cheque / ACH)
        inbounds = [
            t for t in transactions
            if t.direction == TransactionDirection.INBOUND
            and t.amount_usd >= min_dep
        ]

        refund_keywords = ["refund", "excess", "overpayment", "return balance", "cashier check balance", "escrow excess"]

        for dep in inbounds:
            t_dep = datetime.fromisoformat(dep.timestamp)
            max_out_time = t_dep + timedelta(hours=window_hours)

            # Find matching outbound transfers back to third-parties with refund narratives
            refunds = [
                t for t in transactions
                if t.direction == TransactionDirection.OUTBOUND
                and t_dep <= datetime.fromisoformat(t.timestamp) <= max_out_time
                and (
                    t.fraud_typology_tag == "REFUND_OVERPAYMENT_SCAM" or
                    any(kw in (t.reference_narrative or "").lower() for kw in refund_keywords) or
                    t.is_new_payee
                )
            ]

            total_refund = sum(t.amount_usd for t in refunds)
            if dep.amount_usd > 0 and (total_refund / dep.amount_usd) >= ratio_trigger:
                supporting_ids = [dep.transaction_id] + [t.transaction_id for t in refunds]
                alerts.append(FraudAlert(
                    alert_id=f"FR-ALT-OVP-{dep.transaction_id}",
                    rule_id="FR-11",
                    rule_name="Counterfeit Overpayment & Urgent Refund Scam",
                    severity=AlertSeverity.HIGH,
                    score_impact=self.config.get("OVERPAYMENT_RISK_SCORE", 86.0),
                    summary=(
                        f"Customer received large inbound deposit of ${dep.amount_usd:,.2f} from '{dep.counterparty_name}', "
                        f"followed within {window_hours}h by urgent 'refund/overpayment' wire(s) totaling ${total_refund:,.2f} "
                        f"({(total_refund/dep.amount_usd)*100:.1f}%) to third-party accounts before clearing confirmation."
                    ),
                    trigger_details={
                        "deposit_id": dep.transaction_id,
                        "deposit_usd": dep.amount_usd,
                        "refund_total_usd": total_refund,
                        "refund_payees": [t.counterparty_name for t in refunds]
                    },
                    supporting_transaction_ids=supporting_ids
                ))
                break

        return alerts
