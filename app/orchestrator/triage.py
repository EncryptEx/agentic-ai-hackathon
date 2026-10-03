"""Dynamic Triage & Selective Specialist Dispatch Router.

Replaces rigid linear execution with intelligent topology-driven routing,
reducing investigation latency and focusing specialist compute where
risk indicators demand forensic scrutiny.
"""

from enum import Enum
from typing import Dict, Any, List, Optional
import sqlite3
import os

DB_PATH = os.environ.get(
    "FIN_CRIME_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "kyc_aml.db")
)


class CaseTopology(str, Enum):
    CYBER_FRAUD_ATO = "CYBER_FRAUD_ATO"
    APP_SCAM_COERCION = "APP_SCAM_COERCION"
    SMURFING_PASS_THROUGH = "SMURFING_PASS_THROUGH"
    CROSS_BORDER_CORRIDOR = "CROSS_BORDER_CORRIDOR"
    OFFSHORE_SHELL_LAYERING = "OFFSHORE_SHELL_LAYERING"
    STANDARD_BASELINE = "STANDARD_BASELINE"


class DynamicTriageRouter:
    """Evaluates case telemetry and dynamically routes tasks to the optimal specialist sub-swarm."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def triage_case(
        self,
        customer_id: str,
        trigger_alert: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Examines the customer profile and transaction alerts to build an adaptive dispatch plan."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Fetch customer high-level attributes
        cur.execute("SELECT customer_id, first_name, last_name, archetype, type, annual_income_usd, pep_status FROM customers WHERE customer_id = ?", (customer_id,))
        cust_row = cur.fetchone()
        if not cust_row:
            conn.close()
            return {
                "topology": CaseTopology.STANDARD_BASELINE.value,
                "dispatched_specialists": ["customer_agent", "transaction_agent", "fraud_agent", "risk_agent"],
                "hypotheses": ["Customer profile missing; fallback to broad forensic sweep."],
                "rationale": "Missing customer in registry."
            }

        cust_dict = dict(cust_row)

        # 2. Check alerts associated with this customer
        cur.execute("SELECT rule_id, alert_type, severity, rule_name FROM alerts WHERE customer_id = ?", (customer_id,))
        alerts = [dict(r) for r in cur.fetchall()]

        # 3. Check recent transaction channels and volumes
        cur.execute("SELECT transaction_type, direction, amount_usd, counterparty_country, channel FROM transactions WHERE customer_id = ? ORDER BY timestamp DESC LIMIT 30", (customer_id,))
        recent_txs = [dict(r) for r in cur.fetchall()]
        conn.close()

        # Extract diagnostic trigger keys
        trigger_rule = (trigger_alert.get("rule_id", "") if trigger_alert else "").upper()
        alert_rules = {a.get("rule_id", "").upper() for a in alerts}
        has_intl = any(t.get("counterparty_country") not in ("US", "SE", "NO", "DK", None, "") for t in recent_txs)
        has_high_value = any(float(t.get("amount_usd", 0) or 0) > 25000 for t in recent_txs)
        has_crypto_or_wire = any("WIRE" in t.get("transaction_type", "") or "CRYPTO" in t.get("counterparty_category", "") for t in recent_txs)

        # Dynamic topology classification
        if trigger_rule.startswith("FR-01") or "FR-01" in alert_rules or "ATO" in trigger_rule:
            topology = CaseTopology.CYBER_FRAUD_ATO
            specialists = ["customer_agent", "fraud_agent", "transaction_agent", "risk_agent"]
            hypotheses = [
                "H1: Account compromised by unauthorized third-party credential stuffing / session hijacking.",
                "H2: Genuine customer using VPN/proxy attempting first-party chargeback fraud."
            ]
            rationale = "High-severity ATO / session telemetry breach. Prioritize digital identity forensics over corporate UBO."
            token_savings_pct = 25

        elif trigger_rule.startswith("FR-03") or "FR-03" in alert_rules or "COERCION" in trigger_rule or "SCAM" in trigger_rule:
            topology = CaseTopology.APP_SCAM_COERCION
            specialists = ["customer_agent", "fraud_agent", "transaction_agent", "risk_agent"]
            hypotheses = [
                "H1: Authorized Push Payment (APP) coercion: Customer socially engineered into urgent wire transfer.",
                "H2: Deliberate money mule: Customer operating as a paid accomplice in smurfing network."
            ]
            rationale = "Immediate threat to customer funds under active social engineering manipulation."
            token_savings_pct = 20

        elif "TM-01" in alert_rules or "TM-02" in alert_rules or trigger_rule.startswith("TM-01") or trigger_rule.startswith("TM-02"):
            topology = CaseTopology.SMURFING_PASS_THROUGH
            specialists = ["customer_agent", "transaction_agent", "fraud_agent", "risk_agent"]
            hypotheses = [
                "H1: Active money mule pass-through cycle (rapid inbound funds immediately dispersed).",
                "H2: Unintentional pass-through or emergency peer-to-peer liquidity bridge."
            ]
            rationale = "Structuring or pass-through pattern detected. Intensive transaction velocity & counterparty profiling required."
            token_savings_pct = 20

        elif has_intl or cust_dict.get("type") == "corporate" or "TM-05" in alert_rules:
            topology = CaseTopology.OFFSHORE_SHELL_LAYERING if cust_dict.get("type") == "corporate" else CaseTopology.CROSS_BORDER_CORRIDOR
            specialists = ["customer_agent", "transaction_agent", "ownership_agent", "risk_agent"]
            hypotheses = [
                "H1: Illicit capital flight / offshore layering through high-risk secrecy jurisdictions.",
                "H2: Legitimate cross-border trade settlement or international commercial remit."
            ]
            rationale = "International corridors or corporate structure present. Mandatory deep UBO and tax haven scrutiny."
            token_savings_pct = 15

        else:
            topology = CaseTopology.STANDARD_BASELINE
            specialists = ["customer_agent", "transaction_agent", "risk_agent"]
            hypotheses = [
                "H1: Baseline commercial / personal retail banking activity.",
                "H2: Incipient structuring below regulatory reporting thresholds."
            ]
            rationale = "Routine compliance profile. Optimized dispatch eliminates unneeded cyber and offshore specialist passes."
            token_savings_pct = 40

        return {
            "customer_id": customer_id,
            "topology": topology.value,
            "dispatched_specialists": specialists,
            "hypotheses_under_test": hypotheses,
            "rationale": rationale,
            "token_savings_pct": token_savings_pct,
            "active_rules_detected": list(alert_rules),
            "customer_archetype": cust_dict.get("archetype", "RETAIL_INDIVIDUAL")
        }
