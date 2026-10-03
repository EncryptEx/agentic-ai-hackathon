"""Transaction monitoring rules, heuristic anomaly detectors, and behavioral risk scoring."""

from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
from models.customer import CustomerProfile
from models.transaction import Transaction, TransactionDirection, TransactionType
from models.risk_score import AMLAlert, AlertSeverity, PillarScore
from config.rules_config import TM_RULES_CONFIG, RISK_PILLAR_WEIGHTS
from config.jurisdictions import FATF_BLACKLIST, FATF_GREYLIST, SECRECY_OFFSHORE

class TransactionMonitoringDetector:
    """Detects AML typologies and calculates Behavioral Risk Pillar score."""

    def __init__(self, config: Dict[str, Any] = TM_RULES_CONFIG):
        self.config = config

    def analyze_transactions(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> Tuple[List[AMLAlert], PillarScore]:
        """
        Runs all transaction monitoring rules over customer history.
        Returns: (List of AMLAlerts, PillarScore)
        """
        if not transactions:
            # No transactions on record (newly onboarded or zero activity)
            return [], PillarScore(
                pillar_name="Transaction Monitoring & Behavioral Risk",
                weight=RISK_PILLAR_WEIGHTS["TRANSACTION_BEHAVIOR"],
                raw_score=10.0,
                weighted_score=10.0 * RISK_PILLAR_WEIGHTS["TRANSACTION_BEHAVIOR"],
                contributing_factors=["No historical transaction activity on record (Clean baseline)"]
            )

        # Parse transactions and sort
        tx_sorted = sorted(transactions, key=lambda t: t.timestamp)
        alerts: List[AMLAlert] = []

        # Run individual detector rules
        alerts.extend(self._detect_structuring(customer, tx_sorted))
        alerts.extend(self._detect_money_mule_pass_through(customer, tx_sorted))
        alerts.extend(self._detect_turnover_profile_deviation(customer, tx_sorted))
        alerts.extend(self._detect_single_tx_spike(customer, tx_sorted))
        alerts.extend(self._detect_high_risk_corridors(customer, tx_sorted))
        alerts.extend(self._detect_dormancy_break(customer, tx_sorted))
        alerts.extend(self._detect_round_amount_clusters(customer, tx_sorted))
        alerts.extend(self._detect_trade_based_money_laundering(customer, tx_sorted))
        alerts.extend(self._detect_fan_out_layering(customer, tx_sorted))
        alerts.extend(self._detect_cuckoo_smurfing(customer, tx_sorted))
        alerts.extend(self._detect_crypto_mixer_hops(customer, tx_sorted))
        alerts.extend(self._detect_human_trafficking_indicators(customer, tx_sorted))
        alerts.extend(self._detect_loan_collateral_wash(customer, tx_sorted))

        # Calculate behavioral raw score from alerts
        score_impacts = [a.score_impact for a in alerts]
        if not alerts:
            raw_score = 5.0 # baseline clean behavior
            factors = ["All transactions within expected profile boundaries", "No AML typology thresholds breached"]
        else:
            # Diminishing marginal impact formula: highest alert + 50% of secondary alerts
            score_impacts.sort(reverse=True)
            raw_score = score_impacts[0]
            if len(score_impacts) > 1:
                secondary_sum = sum(score_impacts[1:])
                raw_score += secondary_sum * 0.35
            raw_score = min(100.0, max(0.0, raw_score))
            
            factors = [
                f"Triggered {len(alerts)} Transaction Monitoring alert(s):",
                *[f"- [{a.severity.value}] {a.rule_name}: {a.summary}" for a in alerts]
            ]

        weight = RISK_PILLAR_WEIGHTS["TRANSACTION_BEHAVIOR"]
        pillar_score = PillarScore(
            pillar_name="Transaction Monitoring & Behavioral Risk",
            weight=weight,
            raw_score=round(raw_score, 2),
            weighted_score=round(raw_score * weight, 2),
            contributing_factors=factors
        )

        return alerts, pillar_score

    def _detect_structuring(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects Structuring / Smurfing just under $10,000 CTR threshold."""
        alerts = []
        lower = self.config["STRUCTURING_LOWER_BOUND_USD"]
        upper = self.config["STRUCTURING_UPPER_BOUND_USD"]
        window_days = self.config["STRUCTURING_WINDOW_DAYS"]
        min_count = self.config["STRUCTURING_MIN_COUNT"]

        # Filter inbound cash deposits or rapid inbound transfers
        eligible_txs = [
            t for t in transactions
            if t.direction == TransactionDirection.INBOUND
            and lower <= t.amount_usd <= upper
        ]

        if len(eligible_txs) < min_count:
            return alerts

        # Sliding window check
        for i in range(len(eligible_txs)):
            t_start = datetime.fromisoformat(eligible_txs[i].timestamp)
            window_cluster = [eligible_txs[i]]
            for j in range(i + 1, len(eligible_txs)):
                t_curr = datetime.fromisoformat(eligible_txs[j].timestamp)
                if (t_curr - t_start).days <= window_days:
                    window_cluster.append(eligible_txs[j])

            if len(window_cluster) >= min_count:
                total_structured_usd = sum(t.amount_usd for t in window_cluster)
                tx_ids = [t.transaction_id for t in window_cluster]
                alerts.append(AMLAlert(
                    alert_id=f"ALT-STRUC-{customer.customer_id}-{i+1}",
                    rule_id="TM-01",
                    rule_name="Currency Transaction Reporting (CTR) Structuring / Smurfing",
                    severity=AlertSeverity.HIGH if len(window_cluster) == 3 else AlertSeverity.CRITICAL,
                    score_impact=self.config["STRUCTURING_RISK_SCORE"],
                    summary=(
                        f"Detected {len(window_cluster)} inbound deposits totaling ${total_structured_usd:,.2f} "
                        f"in the ${lower:,.0f}-${upper:,.0f} band within {window_days} days. Pattern indicative of intentional threshold evasion."
                    ),
                    trigger_details={
                        "count": len(window_cluster),
                        "total_amount_usd": total_structured_usd,
                        "time_span_days": window_days,
                        "amounts": [t.amount_usd for t in window_cluster]
                    },
                    supporting_transaction_ids=tx_ids
                ))
                break # Avoid duplicate overlapping alerts for same cluster

        return alerts

    def _detect_money_mule_pass_through(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects rapid movement of funds (pass-through / money mule)."""
        alerts = []
        min_inflow = self.config["MULE_MIN_INFLOW_USD"]
        ratio_trigger = self.config["MULE_OUTFLOW_RATIO_TRIGGER"]
        window_hours = self.config["MULE_TIME_WINDOW_HOURS"]

        inbound_wires = [
            t for t in transactions
            if t.direction == TransactionDirection.INBOUND and t.amount_usd >= min_inflow
        ]

        for in_tx in inbound_wires:
            in_time = datetime.fromisoformat(in_tx.timestamp)
            max_out_time = in_time + timedelta(hours=window_hours)

            # Find matching outflows shortly following
            subsequent_outflows = [
                t for t in transactions
                if t.direction == TransactionDirection.OUTBOUND
                and in_time <= datetime.fromisoformat(t.timestamp) <= max_out_time
            ]

            total_out = sum(t.amount_usd for t in subsequent_outflows)
            outflow_ratio = total_out / in_tx.amount_usd if in_tx.amount_usd > 0 else 0.0

            if outflow_ratio >= ratio_trigger:
                supporting_ids = [in_tx.transaction_id] + [t.transaction_id for t in subsequent_outflows]
                alerts.append(AMLAlert(
                    alert_id=f"ALT-MULE-{in_tx.transaction_id}",
                    rule_id="TM-02",
                    rule_name="Rapid Movement of Funds / Pass-Through Account (Money Mule)",
                    severity=AlertSeverity.CRITICAL if outflow_ratio >= 0.90 else AlertSeverity.HIGH,
                    score_impact=self.config["MULE_RISK_SCORE"],
                    summary=(
                        f"Inbound credit of ${in_tx.amount_usd:,.2f} from '{in_tx.counterparty_name}' immediately dissipated "
                        f"({outflow_ratio * 100:.1f}%) within {window_hours} hours via {len(subsequent_outflows)} outbound transfer(s)."
                    ),
                    trigger_details={
                        "inflow_id": in_tx.transaction_id,
                        "inflow_amount_usd": in_tx.amount_usd,
                        "outflow_total_usd": total_out,
                        "drain_percentage": round(outflow_ratio * 100, 1),
                        "counterparties": [t.counterparty_name for t in subsequent_outflows]
                    },
                    supporting_transaction_ids=supporting_ids
                ))
                break

        return alerts

    def _detect_turnover_profile_deviation(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects actual transaction turnover exceeding declared expected turnover."""
        alerts = []
        if not transactions or customer.declared_expected_monthly_turnover_usd <= 0:
            return alerts

        # Estimate time span in months
        t_first = datetime.fromisoformat(transactions[0].timestamp)
        t_last = datetime.fromisoformat(transactions[-1].timestamp)
        span_days = max(14, (t_last - t_first).days + 1)
        span_months = max(1.0, span_days / 30.0)

        total_turnover = sum(t.amount_usd for t in transactions)
        actual_monthly_turnover = total_turnover / span_months
        declared = customer.declared_expected_monthly_turnover_usd
        ratio = actual_monthly_turnover / declared

        if ratio >= self.config["TURNOVER_DEVIATION_HIGH_RATIO"]:
            severity = AlertSeverity.CRITICAL if ratio >= self.config["TURNOVER_DEVIATION_EXTREME_RATIO"] else AlertSeverity.HIGH
            alerts.append(AMLAlert(
                alert_id=f"ALT-VOL-{customer.customer_id}",
                rule_id="TM-03",
                rule_name="Turnover Profile Deviation / Unexpected Volume Spike",
                severity=severity,
                score_impact=80.0 if severity == AlertSeverity.CRITICAL else 65.0,
                summary=(
                    f"Actual monthly turnover (${actual_monthly_turnover:,.2f}/mo) is {ratio:.1f}x higher than declared "
                    f"expected turnover (${declared:,.2f}/mo) across a {span_days}-day monitoring window."
                ),
                trigger_details={
                    "declared_monthly_usd": declared,
                    "actual_monthly_usd": round(actual_monthly_turnover, 2),
                    "deviation_ratio": round(ratio, 2),
                    "total_analyzed_volume_usd": round(total_turnover, 2)
                },
                supporting_transaction_ids=[t.transaction_id for t in transactions[-5:]] # Sample
            ))
        elif ratio >= self.config["TURNOVER_DEVIATION_MODERATE_RATIO"]:
            alerts.append(AMLAlert(
                alert_id=f"ALT-VOL-{customer.customer_id}",
                rule_id="TM-03",
                rule_name="Turnover Profile Deviation (Moderate)",
                severity=AlertSeverity.MEDIUM,
                score_impact=45.0,
                summary=(
                    f"Actual monthly turnover (${actual_monthly_turnover:,.2f}/mo) exceeds declared "
                    f"profile (${declared:,.2f}/mo) by {ratio:.1f}x."
                ),
                trigger_details={
                    "declared_monthly_usd": declared,
                    "actual_monthly_usd": round(actual_monthly_turnover, 2),
                    "deviation_ratio": round(ratio, 2)
                },
                supporting_transaction_ids=[t.transaction_id for t in transactions[-3:]]
            ))

        return alerts

    def _detect_single_tx_spike(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects single transaction outlier vs declared maximum single transaction."""
        alerts = []
        declared_max = customer.declared_expected_max_single_tx_usd
        if declared_max <= 0:
            return alerts

        ratio_trigger = self.config["SINGLE_TX_DEVIATION_RATIO"]
        spikes = [t for t in transactions if t.amount_usd >= (declared_max * ratio_trigger)]

        if spikes:
            highest_tx = max(spikes, key=lambda t: t.amount_usd)
            multiplier = highest_tx.amount_usd / declared_max
            alerts.append(AMLAlert(
                alert_id=f"ALT-SPIKE-{highest_tx.transaction_id}",
                rule_id="TM-04",
                rule_name="Single Transaction Anomaly / Profile Outlier",
                severity=AlertSeverity.HIGH if multiplier >= 8.0 else AlertSeverity.MEDIUM,
                score_impact=60.0 if multiplier >= 8.0 else 40.0,
                summary=(
                    f"Transaction {highest_tx.transaction_id} of ${highest_tx.amount_usd:,.2f} is {multiplier:.1f}x larger "
                    f"than declared maximum single transaction (${declared_max:,.2f})."
                ),
                trigger_details={
                    "transaction_id": highest_tx.transaction_id,
                    "amount_usd": highest_tx.amount_usd,
                    "declared_max_single_tx_usd": declared_max,
                    "multiplier": round(multiplier, 2),
                    "counterparty": highest_tx.counterparty_name
                },
                supporting_transaction_ids=[t.transaction_id for t in spikes]
            ))

        return alerts

    def _detect_high_risk_corridors(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects wire corridors involving FATF Blacklist, Greylist, or Secrecy jurisdictions."""
        alerts = []
        blacklist_txs = []
        greylist_txs = []
        secrecy_txs = []

        for t in transactions:
            cc = t.counterparty_country.upper().strip()
            if cc in FATF_BLACKLIST:
                blacklist_txs.append(t)
            elif cc in FATF_GREYLIST:
                greylist_txs.append(t)
            elif cc in SECRECY_OFFSHORE:
                secrecy_txs.append(t)

        if blacklist_txs:
            total_bl = sum(t.amount_usd for t in blacklist_txs)
            alerts.append(AMLAlert(
                alert_id=f"ALT-CORR-BL-{customer.customer_id}",
                rule_id="TM-05A",
                rule_name="FATF Blacklist / Comprehensive Sanctions Wire Activity",
                severity=AlertSeverity.CRITICAL,
                score_impact=self.config["CORRIDOR_SANCTION_RISK_SCORE"],
                summary=(
                    f"Identified {len(blacklist_txs)} transaction(s) totaling ${total_bl:,.2f} directly involving "
                    f"FATF Call for Action / Blacklist jurisdictions ({', '.join(set(t.counterparty_country for t in blacklist_txs))})."
                ),
                trigger_details={
                    "count": len(blacklist_txs),
                    "total_usd": total_bl,
                    "jurisdictions": list(set(t.counterparty_country for t in blacklist_txs)),
                    "counterparties": [t.counterparty_name for t in blacklist_txs]
                },
                supporting_transaction_ids=[t.transaction_id for t in blacklist_txs]
            ))

        if greylist_txs:
            total_gl = sum(t.amount_usd for t in greylist_txs)
            alerts.append(AMLAlert(
                alert_id=f"ALT-CORR-GL-{customer.customer_id}",
                rule_id="TM-05B",
                rule_name="FATF Greylist / High Risk Third Country Corridor",
                severity=AlertSeverity.HIGH,
                score_impact=self.config["CORRIDOR_GREYLIST_RISK_SCORE"],
                summary=(
                    f"Identified {len(greylist_txs)} transaction(s) totaling ${total_gl:,.2f} involving "
                    f"FATF Greylist jurisdictions ({', '.join(set(t.counterparty_country for t in greylist_txs))})."
                ),
                trigger_details={
                    "count": len(greylist_txs),
                    "total_usd": total_gl,
                    "jurisdictions": list(set(t.counterparty_country for t in greylist_txs)),
                    "counterparties": [t.counterparty_name for t in greylist_txs]
                },
                supporting_transaction_ids=[t.transaction_id for t in greylist_txs]
            ))

        if secrecy_txs and not blacklist_txs and not greylist_txs:
            total_sec = sum(t.amount_usd for t in secrecy_txs)
            alerts.append(AMLAlert(
                alert_id=f"ALT-CORR-SEC-{customer.customer_id}",
                rule_id="TM-05C",
                rule_name="Offshore Secrecy & Tax Haven Financial Corridor",
                severity=AlertSeverity.MEDIUM,
                score_impact=self.config["CORRIDOR_OFFSHORE_RISK_SCORE"],
                summary=(
                    f"Identified {len(secrecy_txs)} transaction(s) totaling ${total_sec:,.2f} involving "
                    f"offshore financial centers ({', '.join(set(t.counterparty_country for t in secrecy_txs))})."
                ),
                trigger_details={
                    "count": len(secrecy_txs),
                    "total_usd": total_sec,
                    "jurisdictions": list(set(t.counterparty_country for t in secrecy_txs))
                },
                supporting_transaction_ids=[t.transaction_id for t in secrecy_txs]
            ))

        return alerts

    def _detect_dormancy_break(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects sudden resumption of high-value activity after extended dormancy."""
        alerts = []
        if len(transactions) < 2:
            return alerts

        min_dormant_days = self.config["DORMANCY_MIN_DAYS_INACTIVE"]
        min_burst_amt = self.config["DORMANCY_BURST_MIN_AMOUNT_USD"]

        for i in range(1, len(transactions)):
            t_prev = datetime.fromisoformat(transactions[i - 1].timestamp)
            t_curr = datetime.fromisoformat(transactions[i].timestamp)
            gap_days = (t_curr - t_prev).days

            if gap_days >= min_dormant_days and transactions[i].amount_usd >= min_burst_amt:
                alerts.append(AMLAlert(
                    alert_id=f"ALT-DORM-{transactions[i].transaction_id}",
                    rule_id="TM-06",
                    rule_name="Dormant Account Reactivation with Large Transaction Flow",
                    severity=AlertSeverity.HIGH,
                    score_impact=65.0,
                    summary=(
                        f"Account remained inactive for {gap_days} days before sudden transaction {transactions[i].transaction_id} "
                        f"of ${transactions[i].amount_usd:,.2f} was executed."
                    ),
                    trigger_details={
                        "gap_days": gap_days,
                        "amount_usd": transactions[i].amount_usd,
                        "counterparty": transactions[i].counterparty_name
                    },
                    supporting_transaction_ids=[transactions[i].transaction_id]
                ))
                break

        return alerts

    def _detect_round_amount_clusters(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects repetitive round amounts ($1,000, $5,000, $10,000)."""
        alerts = []
        min_count = self.config["ROUND_AMOUNT_MIN_COUNT"]
        window_days = self.config["ROUND_AMOUNT_WINDOW_DAYS"]

        round_txs = [
            t for t in transactions
            if t.amount_usd >= 1000.0 and t.amount_usd % 1000.0 == 0.0
        ]

        if len(round_txs) >= min_count:
            # Check if within window
            t_first = datetime.fromisoformat(round_txs[0].timestamp)
            t_last = datetime.fromisoformat(round_txs[-1].timestamp)
            if (t_last - t_first).days <= window_days:
                total_round = sum(t.amount_usd for t in round_txs)
                alerts.append(AMLAlert(
                    alert_id=f"ALT-ROUND-{customer.customer_id}",
                    rule_id="TM-07",
                    rule_name="Cluster of Repetitive Round-Dollar Amounts",
                    severity=AlertSeverity.MEDIUM,
                    score_impact=40.0,
                    summary=(
                        f"Identified {len(round_txs)} transactions with exact round multiples totaling ${total_round:,.2f} "
                        f"within {window_days} days without commercial fractional cents."
                    ),
                    trigger_details={
                        "count": len(round_txs),
                        "total_amount_usd": total_round,
                        "amounts": [t.amount_usd for t in round_txs]
                    },
                    supporting_transaction_ids=[t.transaction_id for t in round_txs]
                ))

        return alerts

    def _detect_trade_based_money_laundering(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects Trade-Based Money Laundering (TBML) & Over/Under-Invoicing (TM-08)."""
        alerts = []
        min_invoice = self.config.get("TBML_MIN_INVOICE_AMOUNT_USD", 25000.0)
        tbml_keywords = [
            "commercial invoice", "consignment", "bill of lading", "freight customs",
            "raw material shipment", "bulk textile", "electronics container", "re-export settlement"
        ]

        tbml_txs = []
        for t in transactions:
            is_tag = t.synthetic_typology_tag == "TBML_OVER_INVOICING"
            narrative_lower = (t.reference_narrative or "").lower()
            has_tbml_signal = any(kw in narrative_lower for kw in tbml_keywords)

            # High value cross-border commercial wire inconsistent with retail banking
            is_high_wire = (
                t.transaction_type in [TransactionType.INTERNATIONAL_WIRE_IN, TransactionType.INTERNATIONAL_WIRE_OUT] and
                t.amount_usd >= min_invoice
            )
            if is_tag or (is_high_wire and has_tbml_signal):
                tbml_txs.append(t)

        if len(tbml_txs) >= self.config.get("TBML_MIN_TRANSACTIONS", 2) or any(t.synthetic_typology_tag == "TBML_OVER_INVOICING" for t in tbml_txs):
            if tbml_txs:
                total_tbml = sum(t.amount_usd for t in tbml_txs)
                alerts.append(AMLAlert(
                    alert_id=f"ALT-TBML-{customer.customer_id}",
                    rule_id="TM-08",
                    rule_name="Trade-Based Money Laundering (TBML) & Over/Under-Invoicing",
                    severity=AlertSeverity.HIGH if total_tbml < 100000.0 else AlertSeverity.CRITICAL,
                    score_impact=self.config.get("TBML_RISK_SCORE", 88.0),
                    summary=(
                        f"Detected {len(tbml_txs)} high-value international trade wire(s) totaling ${total_tbml:,.2f} "
                        f"referencing commercial shipping/freight invoices ({', '.join(set(t.counterparty_country for t in tbml_txs))}). "
                        f"Retail banking account utilized for substantial cross-border commercial cargo settlements."
                    ),
                    trigger_details={
                        "count": len(tbml_txs),
                        "total_amount_usd": total_tbml,
                        "counterparties": [t.counterparty_name for t in tbml_txs],
                        "countries": list(set(t.counterparty_country for t in tbml_txs))
                    },
                    supporting_transaction_ids=[t.transaction_id for t in tbml_txs]
                ))

        return alerts

    def _detect_fan_out_layering(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects Fan-Out Layering / High-Velocity Fund Distribution (TM-09)."""
        alerts = []
        min_inflow = self.config.get("FAN_OUT_MIN_INFLOW_USD", 15000.0)
        min_splits = self.config.get("FAN_OUT_MIN_SPLITS", 4)
        window_hours = self.config.get("FAN_OUT_WINDOW_HOURS", 36)

        # Inbound credits
        inbound_txs = [
            t for t in transactions
            if t.direction == TransactionDirection.INBOUND and t.amount_usd >= min_inflow
        ]

        for in_tx in inbound_txs:
            t_in = datetime.fromisoformat(in_tx.timestamp)
            max_out_time = t_in + timedelta(hours=window_hours)

            out_splits = [
                t for t in transactions
                if t.direction == TransactionDirection.OUTBOUND
                and t_in <= datetime.fromisoformat(t.timestamp) <= max_out_time
            ]

            is_tag = any(t.synthetic_typology_tag == "FAN_OUT_LAYERING" for t in out_splits)
            if (len(out_splits) >= min_splits or is_tag) and out_splits:
                total_out = sum(t.amount_usd for t in out_splits)
                if (total_out / in_tx.amount_usd) >= 0.75 or is_tag:
                    alerts.append(AMLAlert(
                        alert_id=f"ALT-FANOUT-{in_tx.transaction_id}",
                        rule_id="TM-09",
                        rule_name="Fan-Out Layering / High-Velocity Fund Distribution",
                        severity=AlertSeverity.CRITICAL,
                        score_impact=self.config.get("FAN_OUT_RISK_SCORE", 87.0),
                        summary=(
                            f"Single inbound credit of ${in_tx.amount_usd:,.2f} immediately fragmented and disbursed "
                            f"across {len(out_splits)} distinct outbound transfers totaling ${total_out:,.2f} within {window_hours} hours. "
                            f"Typology breaks audit trail across multiple channels/beneficiaries."
                        ),
                        trigger_details={
                            "inflow_id": in_tx.transaction_id,
                            "inflow_amount_usd": in_tx.amount_usd,
                            "splits_count": len(out_splits),
                            "total_outflow_usd": total_out,
                            "payees": [t.counterparty_name for t in out_splits]
                        },
                        supporting_transaction_ids=[in_tx.transaction_id] + [t.transaction_id for t in out_splits]
                    ))
                    break

        return alerts

    def _detect_cuckoo_smurfing(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects Cuckoo Smurfing / Hawala Alternate Remittance Deposits (TM-10)."""
        alerts = []
        min_deposits = self.config.get("CUCKOO_MIN_UNRELATED_DEPOSITS", 3)

        # Look for multiple unrelated third party inbound transfers/deposits
        inbound_deposits = [
            t for t in transactions
            if t.direction == TransactionDirection.INBOUND
            and t.transaction_type in [TransactionType.DOMESTIC_WIRE_IN, TransactionType.ACH_DEPOSIT, TransactionType.CASH_DEPOSIT, TransactionType.P2P_TRANSFER_IN]
            and t.counterparty_category in ["INDIVIDUAL", "PEER", "ATM_BRANCH", "OFFSHORE_CORP"]
        ]

        cuckoo_tagged = [t for t in inbound_deposits if t.synthetic_typology_tag == "CUCKOO_SMURFING"]

        # Check for multiple distinct third-party payers within a 10-day window
        if cuckoo_tagged or len(inbound_deposits) >= min_deposits:
            target_list = cuckoo_tagged if cuckoo_tagged else inbound_deposits
            unique_payers = set(t.counterparty_name for t in target_list)
            if len(unique_payers) >= 3 or cuckoo_tagged:
                total_in = sum(t.amount_usd for t in target_list)
                if total_in >= 12000.0 or cuckoo_tagged:
                    alerts.append(AMLAlert(
                        alert_id=f"ALT-CUCKOO-{customer.customer_id}",
                        rule_id="TM-10",
                        rule_name="Cuckoo Smurfing & Hawala Third-Party Remittance Matching",
                        severity=AlertSeverity.HIGH,
                        score_impact=self.config.get("CUCKOO_RISK_SCORE", 86.0),
                        summary=(
                            f"Account received {len(target_list)} unrelated inbound transfers totaling ${total_in:,.2f} "
                            f"from {len(unique_payers)} distinct third-party remitters without commercial justification. "
                            f"Typology matches alternative remittance smurfing / Hawala integration."
                        ),
                        trigger_details={
                            "deposit_count": len(target_list),
                            "total_inbound_usd": total_in,
                            "remitters": list(unique_payers)
                        },
                        supporting_transaction_ids=[t.transaction_id for t in target_list]
                    ))

        return alerts

    def _detect_crypto_mixer_hops(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects Crypto Mixers, Tumblers & Darknet Ramps (TM-11)."""
        alerts = []
        mixer_keywords = [
            "tornado cash", "wasabi", "sinbad", "blender.io", "railgun",
            "coinjoin", "mixer", "tumbler", "privacy pool", "unhosted anonymizer"
        ]

        mixer_txs = []
        for t in transactions:
            is_tag = t.synthetic_typology_tag == "CRYPTO_MIXER_HOP"
            narrative_lower = (t.reference_narrative or "").lower()
            cp_lower = (t.counterparty_name or "").lower()
            has_mixer = any(kw in narrative_lower or kw in cp_lower for kw in mixer_keywords)

            if is_tag or has_mixer or (t.counterparty_category == "CRYPTO_MIXER"):
                mixer_txs.append(t)

        if mixer_txs:
            total_mixer = sum(t.amount_usd for t in mixer_txs)
            alerts.append(AMLAlert(
                alert_id=f"ALT-MIXER-{customer.customer_id}",
                rule_id="TM-11",
                rule_name="Crypto Mixer, Tumbler & Anonymity Protocol Interaction",
                severity=AlertSeverity.CRITICAL,
                score_impact=self.config.get("MIXER_RISK_SCORE", 96.0),
                summary=(
                    f"Direct financial interaction identified with sanctioned/anonymizing virtual asset mixer(s) "
                    f"({', '.join(set(t.counterparty_name for t in mixer_txs))}) totaling ${total_mixer:,.2f}. "
                    f"Severe money laundering indicator for source-of-funds obfuscation."
                ),
                trigger_details={
                    "count": len(mixer_txs),
                    "total_usd": total_mixer,
                    "mixers": [t.counterparty_name for t in mixer_txs],
                    "narratives": [t.reference_narrative for t in mixer_txs]
                },
                supporting_transaction_ids=[t.transaction_id for t in mixer_txs]
            ))

        return alerts

    def _detect_human_trafficking_indicators(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects Human Trafficking & Labor Exploitation Financial Red Flags (TM-12)."""
        alerts = []
        trafficking_keywords = [
            "worker wage deduction", "hostel bunk", "transit lodging", "van shuttle group",
            "recruitment fee deduction", "labor dormitory", "human trafficking", "centralized wage pooling"
        ]

        ht_txs = []
        for t in transactions:
            is_tag = t.synthetic_typology_tag == "HUMAN_TRAFFICKING_RED_FLAGS"
            narrative_lower = (t.reference_narrative or "").lower()
            has_ht_keywords = any(kw in narrative_lower for kw in trafficking_keywords)

            # Funnel account: late night repetitive cash extractions in border/transit corridors
            is_late_night_cash = (
                t.transaction_type in [TransactionType.ATM_WITHDRAWAL, TransactionType.CASH_WITHDRAWAL] and
                t.channel in ["ATM", "BRANCH_TELLER"]
            )
            if is_tag or has_ht_keywords or (is_late_night_cash and is_tag):
                ht_txs.append(t)

        if len(ht_txs) >= self.config.get("TRAFFICKING_REPETITIVE_MIN_TX", 3) or any(t.synthetic_typology_tag == "HUMAN_TRAFFICKING_RED_FLAGS" for t in ht_txs):
            if ht_txs:
                total_amt = sum(t.amount_usd for t in ht_txs)
                alerts.append(AMLAlert(
                    alert_id=f"ALT-HT-{customer.customer_id}",
                    rule_id="TM-12",
                    rule_name="Human Trafficking & Modern Slavery Labor Exploitation Red Flags",
                    severity=AlertSeverity.CRITICAL,
                    score_impact=self.config.get("TRAFFICKING_RISK_SCORE", 93.0),
                    summary=(
                        f"Financial telemetry exhibits {len(ht_txs)} indicators of human trafficking / labor exploitation: "
                        f"centralized wage skimming, rapid cash depletion, and transit lodging payments totaling ${total_amt:,.2f}."
                    ),
                    trigger_details={
                        "indicators_count": len(ht_txs),
                        "total_volume_usd": total_amt,
                        "counterparties": [t.counterparty_name for t in ht_txs]
                    },
                    supporting_transaction_ids=[t.transaction_id for t in ht_txs]
                ))

        return alerts

    def _detect_loan_collateral_wash(
        self,
        customer: CustomerProfile,
        transactions: List[Transaction]
    ) -> List[AMLAlert]:
        """Detects Loan Collateral Laundering & Rapid Liquidation Wash (TM-13)."""
        alerts = []
        min_loan = self.config.get("LOAN_WASH_MIN_AMOUNT_USD", 20000.0)

        loan_keywords = ["loan disbursement", "credit line draw", "commercial advance"]
        payoff_keywords = ["early payoff", "loan settlement full", "credit line liquidation", "collateral release"]

        # Inbound loan
        loan_in = [
            t for t in transactions
            if t.direction == TransactionDirection.INBOUND
            and (t.synthetic_typology_tag == "LOAN_COLLATERAL_WASH" or any(kw in (t.reference_narrative or "").lower() for kw in loan_keywords))
            and t.amount_usd >= min_loan
        ]

        for loan in loan_in:
            t_loan = datetime.fromisoformat(loan.timestamp)
            max_payoff_time = t_loan + timedelta(days=self.config.get("LOAN_WASH_MAX_DAYS_TO_PAYOFF", 30))

            payoffs = [
                t for t in transactions
                if t.direction == TransactionDirection.OUTBOUND
                and t_loan <= datetime.fromisoformat(t.timestamp) <= max_payoff_time
                and (
                    t.synthetic_typology_tag == "LOAN_COLLATERAL_WASH" or
                    any(kw in (t.reference_narrative or "").lower() for kw in payoff_keywords) or
                    t.amount_usd >= (loan.amount_usd * 0.90)
                )
            ]

            if payoffs:
                total_payoff = sum(t.amount_usd for t in payoffs)
                alerts.append(AMLAlert(
                    alert_id=f"ALT-LOAN-{loan.transaction_id}",
                    rule_id="TM-13",
                    rule_name="Loan Collateral Laundering & Rapid Early Liquidation",
                    severity=AlertSeverity.HIGH,
                    score_impact=self.config.get("LOAN_WASH_RISK_SCORE", 84.0),
                    summary=(
                        f"Loan disbursement of ${loan.amount_usd:,.2f} rapidly settled/liquidated within "
                        f"{(datetime.fromisoformat(payoffs[0].timestamp) - t_loan).days} days via ${total_payoff:,.2f} "
                        f"repayment from external unverified funds, effectively converting illicit cash into clean payoff credit."
                    ),
                    trigger_details={
                        "loan_id": loan.transaction_id,
                        "loan_amount_usd": loan.amount_usd,
                        "payoff_total_usd": total_payoff,
                        "days_to_payoff": (datetime.fromisoformat(payoffs[0].timestamp) - t_loan).days
                    },
                    supporting_transaction_ids=[loan.transaction_id] + [t.transaction_id for t in payoffs]
                ))
                break

        return alerts
