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
