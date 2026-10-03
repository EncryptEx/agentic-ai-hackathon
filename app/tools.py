"""Investigation tools backed by the unified FRAML SQLite dataset and Risk Engine.

Every function here is a plain Python callable that ADK can expose to an
agent as a tool. They query the unified SQLite database managed by
``storage.database.DatabaseManager`` and integrate with the multi-pillar KYC,
AML, and Fraud risk engine.

ALL DATA IS SYNTHETIC AND FICTIONAL.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from config.jurisdictions import (
    FATF_BLACKLIST,
    FATF_GREYLIST,
    LOW_RISK_COUNTRIES,
    MEDIUM_RISK_COUNTRIES,
    SECRECY_OFFSHORE,
    evaluate_country_risk,
)
from storage.database import DEFAULT_DB_PATH, DatabaseManager

# --------------------------------------------------------------------------
# Connection helper
# --------------------------------------------------------------------------

_DB_MANAGER: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get or initialize the singleton DatabaseManager."""
    global _DB_MANAGER
    if _DB_MANAGER is None:
        _DB_MANAGER = DatabaseManager(DEFAULT_DB_PATH)
    return _DB_MANAGER


def _connect() -> sqlite3.Connection:
    """Open the unified database connection."""
    db_mgr = get_db_manager()
    return db_mgr._get_connection()


def _rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Customer & KYC Tools
# --------------------------------------------------------------------------


def list_customers() -> list[dict[str, Any]]:
    """List synthetic customers available for investigation.

    Returns:
        A list of customers with id, name, type, country, risk rating, and archetype.
    """
    return _rows(
        "SELECT customer_id, name, type, country, risk_rating, archetype "
        "FROM customers ORDER BY customer_id"
    )


def get_customer_profile(customer_id: str) -> dict[str, Any]:
    """Get the full profile for one synthetic customer.

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        The customer profile record, or an error dict if not found.
    """
    rows = _rows("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    if not rows:
        return {"error": f"No customer found with id {customer_id!r}."}
    profile = rows[0]
    if profile.get("products_held") and isinstance(profile["products_held"], str):
        try:
            profile["products_held"] = json.loads(profile["products_held"])
        except Exception:
            pass
    if profile.get("synthetic_id_indicators") and isinstance(profile["synthetic_id_indicators"], str):
        try:
            profile["synthetic_id_indicators"] = json.loads(profile["synthetic_id_indicators"])
        except Exception:
            pass
    return profile


def get_kyc_dossier(customer_id: str) -> dict[str, Any]:
    """Retrieve the full Customer Due Diligence (CDD) KYC dossier for a customer.

    Provides comprehensive demographic, economic, wealth plausibility, product,
    and watchlist screening data (PEP, adverse media, sanctions) from the KYC engine.

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        A structured KYC dossier including identity, wealth plausibility, and watchlists.
    """
    profile = get_customer_profile(customer_id)
    if "error" in profile:
        return profile

    income = float(profile.get("annual_income_usd") or 0.0)
    wealth = float(profile.get("net_worth_usd") or 0.0)
    wealth_ratio = round(wealth / income, 1) if income > 0 else None

    declared_turnover = float(profile.get("declared_expected_monthly_turnover_usd") or 0.0)
    monthly_income = round(income / 12.0, 2) if income > 0 else 0.0
    turnover_ratio = round(declared_turnover / monthly_income, 1) if monthly_income > 0 else None

    return {
        "customer_id": customer_id,
        "name": profile.get("name"),
        "archetype": profile.get("archetype"),
        "demographics": {
            "date_of_birth": profile.get("date_of_birth"),
            "age": profile.get("age"),
            "citizenship": profile.get("citizenship"),
            "dual_citizenship": profile.get("dual_citizenship"),
            "residence_country": profile.get("residence_country") or profile.get("country"),
            "tax_residence_country": profile.get("tax_residence_country"),
            "address": {
                "line": profile.get("address_line"),
                "city": profile.get("address_city"),
                "postal_code": profile.get("address_postal_code"),
            },
        },
        "employment_and_economic_profile": {
            "occupation": profile.get("occupation"),
            "occupation_risk_key": profile.get("occupation_risk_key"),
            "industry": profile.get("industry"),
            "employer_name": profile.get("employer_name"),
        },
        "financial_and_wealth_plausibility": {
            "annual_income_usd": income,
            "net_worth_usd": wealth,
            "wealth_to_income_ratio": wealth_ratio,
            "source_of_funds": profile.get("source_of_funds"),
            "source_of_wealth": profile.get("source_of_wealth"),
            "declared_expected_monthly_turnover_usd": declared_turnover,
            "turnover_to_monthly_salary_ratio": turnover_ratio,
            "declared_expected_max_single_tx_usd": profile.get("declared_expected_max_single_tx_usd"),
        },
        "account_purpose_and_products": {
            "declared_purpose": profile.get("declared_purpose_nature"),
            "onboarding_channel": profile.get("onboarding_channel"),
            "onboarding_date": profile.get("onboarding_date") or profile.get("onboarded"),
            "products_held": profile.get("products_held"),
        },
        "screening_and_watchlists": {
            "pep_status": profile.get("pep_status"),
            "pep_details": profile.get("pep_details"),
            "adverse_media": profile.get("adverse_media"),
            "adverse_media_details": profile.get("adverse_media_details"),
            "sanction_status": profile.get("sanction_status"),
            "sanction_details": profile.get("sanction_details"),
        },
        "digital_footprint_summary": {
            "email_domain_type": profile.get("email_domain_type"),
            "phone_line_type": profile.get("phone_line_type"),
            "synthetic_identity_score": profile.get("synthetic_identity_score"),
            "synthetic_id_indicators": profile.get("synthetic_id_indicators"),
        },
    }


# --------------------------------------------------------------------------
# Transaction Monitoring & AML Tools
# --------------------------------------------------------------------------


def get_transactions(customer_id: str) -> list[dict[str, Any]]:
    """Get all synthetic transactions for a customer, oldest first.

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        A list of transactions with amounts, channels, and counterparty metadata.
    """
    return _rows(
        "SELECT transaction_id, date, timestamp, kind, direction, amount, amount_usd, "
        "channel, description, reference_narrative, counterparty_name, "
        "counterparty_country, counterparty_category, device_id, ip_address, "
        "auth_status, is_card_present, card_entry_mode, is_new_payee "
        "FROM transactions WHERE customer_id = ? ORDER BY timestamp",
        (customer_id,),
    )


def get_expected_activity(customer_id: str) -> dict[str, Any]:
    """Get the expected monthly activity profile for a customer.

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        The expected volume, count and description, or an error dict.
    """
    rows = _rows(
        "SELECT * FROM expected_activity WHERE customer_id = ?", (customer_id,)
    )
    if not rows:
        return {"error": f"No expected activity profile for {customer_id!r}."}
    return rows[0]


def get_transaction_alerts(customer_id: str) -> list[dict[str, Any]]:
    """Retrieve all triggered AML transaction monitoring alerts for a customer.

    Alerts are generated by the Transaction Monitoring Detector rules:
    - TM-01: Structuring / Smurfing (below $10,000 CTR threshold)
    - TM-02: Rapid Movement of Funds / Money Mule Pass-Through
    - TM-03: Turnover Profile Deviation / Unexpected Volume Spike
    - TM-04: Single Transaction Anomaly / Outlier Spike
    - TM-05: High-Risk Geographic Corridors (Blacklist, Greylist, Offshore Secrecy)
    - TM-06: Dormant Account Reactivation Surge
    - TM-07: Repetitive Round-Dollar Amount Clusters

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        A list of triggered AML alert dictionaries with severity and transaction evidence.
    """
    raw_alerts = _rows("SELECT * FROM alerts WHERE customer_id = ? AND (alert_type = 'AML' OR alert_type IS NULL)", (customer_id,))
    parsed_alerts = []
    for a in raw_alerts:
        trigger = a.get("trigger_details")
        supporting = a.get("supporting_transaction_ids")
        if trigger and isinstance(trigger, str):
            try:
                trigger = json.loads(trigger)
            except Exception:
                pass
        if supporting and isinstance(supporting, str):
            try:
                supporting = json.loads(supporting)
            except Exception:
                pass
        parsed_alerts.append(
            {
                "alert_id": a.get("alert_id"),
                "customer_id": a.get("customer_id"),
                "rule_id": a.get("rule_id"),
                "rule_name": a.get("rule_name"),
                "severity": a.get("severity"),
                "score_impact": a.get("score_impact"),
                "summary": a.get("summary"),
                "trigger_details": trigger,
                "supporting_transaction_ids": supporting,
            }
        )
    return parsed_alerts


def analyze_transactions(customer_id: str) -> dict[str, Any]:
    """Compute summary statistics and flag anomalies for a customer's transactions.

    Flags include: volume vs expected, count vs expected, cash intensity,
    deposits just below the 10,000 reporting threshold, rapid pass-through,
    and rule-based transaction monitoring (TM) alerts.

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        A dict of computed metrics, anomaly flags, and triggered TM rule alerts.
    """
    txns = get_transactions(customer_id)
    expected = get_expected_activity(customer_id)

    if not txns:
        return {"customer_id": customer_id, "transaction_count": 0, "flags": [], "tm_alerts": []}

    total = sum(t["amount"] for t in txns)
    count = len(txns)
    deposits = [t for t in txns if t["direction"] == "INBOUND" or t["kind"] in ("deposit", "salary_credit", "wire_in", "p2p_transfer_in", "ach_deposit")]
    outbound = [t for t in txns if t["direction"] == "OUTBOUND" or t["kind"] in ("withdrawal", "ach_withdrawal", "p2p_transfer_out", "wire_out", "crypto_purchase", "pos_purchase", "online_purchase")]
    cash = [t for t in txns if t.get("channel") in ("cash", "CASH", "ATM", "BRANCH_TELLER") or "cash" in t["kind"].lower()]

    # Deposits in the 7,500-9,999 band (just under the 10,000 threshold).
    near_threshold = [t for t in deposits if 7500 <= t["amount"] < 10000]

    flags: list[dict[str, Any]] = []

    if "expected_monthly_volume" in expected:
        exp_vol = expected["expected_monthly_volume"]
        if exp_vol and total > exp_vol * 1.5:
            flags.append(
                {
                    "flag": "volume_above_expected",
                    "detail": (
                        f"Total volume {total:,.2f} is "
                        f"{total / exp_vol:.1f}x the expected monthly "
                        f"volume of {exp_vol:,.2f}."
                    ),
                }
            )

    if "expected_monthly_count" in expected:
        exp_cnt = expected["expected_monthly_count"]
        if exp_cnt and count > exp_cnt * 1.5:
            flags.append(
                {
                    "flag": "count_above_expected",
                    "detail": (
                        f"{count} transactions vs expected {exp_cnt} "
                        f"({count / exp_cnt:.1f}x)."
                    ),
                }
            )

    if near_threshold:
        flags.append(
            {
                "flag": "possible_structuring",
                "detail": (
                    f"{len(near_threshold)} deposits between $7,500 and "
                    f"$9,999 (evading the $10,000 CTR threshold), "
                    f"totalling ${sum(t['amount'] for t in near_threshold):,.2f}."
                ),
            }
        )

    if deposits and len(cash) / len(deposits) > 0.5:
        flags.append(
            {
                "flag": "high_cash_intensity",
                "detail": (
                    f"{len(cash)} of {len(deposits)} transactions are cash "
                    f"({len(cash) / len(deposits):.0%})."
                ),
            }
        )

    tm_alerts = get_transaction_alerts(customer_id)

    return {
        "customer_id": customer_id,
        "transaction_count": count,
        "total_volume": round(total, 2),
        "deposit_count": len(deposits),
        "outbound_count": len(outbound),
        "cash_count": len(cash),
        "near_threshold_deposits": len(near_threshold),
        "expected": expected,
        "flags": flags,
        "tm_alerts": tm_alerts,
        "tm_rules_triggered": [f"{a['rule_id']} ({a['rule_name']})" for a in tm_alerts],
    }


# --------------------------------------------------------------------------
# Fraud & Cybercrime Detection Tools
# --------------------------------------------------------------------------


def get_fraud_alerts(customer_id: str) -> list[dict[str, Any]]:
    """Retrieve all triggered Fraud & Cybercrime alerts for a customer.

    Alerts are generated by the Fraud Detection rules:
    - FR-01: Account Takeover (ATO) & Impossible Travel Velocity (>900 km/h)
    - FR-02: Card Testing / Micro-probing followed by high-dollar drain
    - FR-03: Authorized Push Payment (APP) / Investment or Romance Scams
    - FR-04: First-Party Bust-Out / Deposit Kiting Fraud
    - FR-05: Synthetic Identity Fraud & Disposable Burner Credentials

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        A list of triggered Fraud alert dictionaries with telemetry and transaction evidence.
    """
    raw_alerts = _rows("SELECT * FROM alerts WHERE customer_id = ? AND alert_type = 'FRAUD'", (customer_id,))
    parsed_alerts = []
    for a in raw_alerts:
        trigger = a.get("trigger_details")
        supporting = a.get("supporting_transaction_ids")
        if trigger and isinstance(trigger, str):
            try:
                trigger = json.loads(trigger)
            except Exception:
                pass
        if supporting and isinstance(supporting, str):
            try:
                supporting = json.loads(supporting)
            except Exception:
                pass
        parsed_alerts.append(
            {
                "alert_id": a.get("alert_id"),
                "customer_id": a.get("customer_id"),
                "rule_id": a.get("rule_id"),
                "rule_name": a.get("rule_name"),
                "severity": a.get("severity"),
                "score_impact": a.get("score_impact"),
                "summary": a.get("summary"),
                "trigger_details": trigger,
                "supporting_transaction_ids": supporting,
            }
        )
    return parsed_alerts


def get_digital_telemetry(customer_id: str) -> dict[str, Any]:
    """Retrieve digital identity, device fingerprints, and authentication telemetry.

    Provides fraud forensic signals:
    - Device primary ID and recognized devices
    - IP addresses and geographic locations
    - Disposable temporary email domain detection
    - Virtual VoIP line detection
    - Card entry modes (CHIP_EMV, CONTACTLESS, CNP_ECOMMERCE)
    - Transaction authorization status (DECLINED_SUSPECTED_FRAUD)
    - New payee velocity (first seen hours)
    - Synthetic identity anomaly score

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        Digital identity and cyber telemetry signals for fraud analysis.
    """
    profile = get_customer_profile(customer_id)
    if "error" in profile:
        return profile

    txns = get_transactions(customer_id)
    unique_devices = list({t["device_id"] for t in txns if t.get("device_id")})
    unique_ips = list({t["ip_address"] for t in txns if t.get("ip_address")})
    declined_txs = [t for t in txns if "DECLINED" in (t.get("auth_status") or "")]
    new_payee_txs = [t for t in txns if t.get("is_new_payee")]

    return {
        "customer_id": customer_id,
        "digital_identity": {
            "email_address": profile.get("email_address"),
            "email_domain_type": profile.get("email_domain_type"),
            "phone_number": profile.get("phone_number"),
            "phone_line_type": profile.get("phone_line_type"),
            "primary_ip_address": profile.get("primary_ip_address"),
            "primary_ip_country": profile.get("primary_ip_country"),
            "primary_device_id": profile.get("device_primary_id"),
        },
        "synthetic_identity_assessment": {
            "score": profile.get("synthetic_identity_score") or 0.0,
            "risk_level": "CRITICAL" if (profile.get("synthetic_identity_score") or 0) >= 60 else "LOW",
            "indicators": profile.get("synthetic_id_indicators") or [],
        },
        "session_and_device_telemetry": {
            "devices_observed": unique_devices,
            "ips_observed": unique_ips,
            "device_count": len(unique_devices),
            "multiple_device_access": len(unique_devices) > 1,
            "declined_auth_attempts": len(declined_txs),
            "new_payee_transfers": len(new_payee_txs),
        },
    }


# --------------------------------------------------------------------------
# Ownership & Country Risk Tools
# --------------------------------------------------------------------------


def get_ownership_structure(customer_id: str) -> dict[str, Any]:
    """Get the synthetic ownership and control structure for a customer.

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        Shareholders and directors, with jurisdictions and stakes.
    """
    rows = _rows(
        "SELECT entity, country, stake, role, note FROM ownership "
        "WHERE customer_id = ? ORDER BY role, stake DESC",
        (customer_id,),
    )
    if not rows:
        return {"customer_id": customer_id, "shareholders": [], "directors": []}
    return {
        "customer_id": customer_id,
        "shareholders": [r for r in rows if r["role"] == "shareholder"],
        "directors": [r for r in rows if r["role"] == "director"],
        "employers": [r for r in rows if r["role"] == "employer"],
    }


def get_country_risk(country: str) -> dict[str, Any]:
    """Get the synthetic risk rating for a country.

    Args:
        country: The country name or ISO-2 code, e.g. "Panama" or "PA".

    Returns:
        The rating and rationale, or an error dict if unknown.
    """
    rows = _rows("SELECT * FROM country_risk WHERE country = ? OR country_code = ?", (country, country.upper()))
    if rows:
        d = dict(rows[0])
        d["country"] = country
        return d

    cc = country.upper().strip()
    if (
        cc in FATF_BLACKLIST
        or cc in FATF_GREYLIST
        or cc in SECRECY_OFFSHORE
        or cc in MEDIUM_RISK_COUNTRIES
        or cc in LOW_RISK_COUNTRIES
    ):
        level, score, reasons = evaluate_country_risk(cc)
        return {
            "country": country,
            "country_code": cc,
            "rating": level.lower(),
            "rationale": " | ".join(reasons),
            "risk_score": score,
        }

    return {"error": f"No country risk rating for {country!r}."}


# --------------------------------------------------------------------------
# Multi-Pillar FRAML Risk Assessment & Alert Feed Tools
# --------------------------------------------------------------------------


def get_risk_assessment(customer_id: str) -> dict[str, Any]:
    """Retrieve the multi-pillar FRAML risk assessment generated by the Risk Engine.

    Evaluates the customer across 5 weighted pillars on a 0-100 scale:
    - Pillar 1: Customer KYC & Demographics (20% weight)
    - Pillar 2: Purpose & Nature of Relationship (10% weight)
    - Pillar 3: Products & Onboarding Channels (10% weight)
    - Pillar 4: AML Transaction Monitoring & Behavioral Risk (30% weight)
    - Pillar 5: Fraud Risk & Digital Footprint (30% weight)

    Also returns:
    - Composite Score (0-100) and assigned Risk Tier (LOW, MEDIUM, HIGH, CRITICAL)
    - Separate AML Sub-Score and Fraud Sub-Score
    - Regulatory & Fraud Overrides applied (Sanctions, Blacklist corridors, ATO, Bust-out, Structuring)
    - Itemized AML alerts count and Fraud alerts count
    - Concrete operational compliance audit action checklist

    Args:
        customer_id: The customer identifier, e.g. "CUST-00015" or "CUST-00001".

    Returns:
        Complete 5-pillar FRAML risk assessment breakdown with audit checklist.
    """
    rows = _rows("SELECT * FROM risk_assessments WHERE customer_id = ?", (customer_id,))
    if not rows:
        return {"error": f"No risk assessment found for customer {customer_id!r}."}

    raw = rows[0]
    checklist = raw.get("action_checklist")
    if checklist and isinstance(checklist, str):
        try:
            checklist = json.loads(checklist)
        except Exception:
            pass

    return {
        "customer_id": customer_id,
        "assessment_timestamp": raw.get("assessment_timestamp"),
        "composite_score": raw.get("composite_score"),
        "risk_tier": raw.get("risk_tier"),
        "sub_scores": {
            "aml_score": raw.get("aml_score"),
            "fraud_score": raw.get("fraud_score"),
        },
        "pillars": {
            "kyc_demographics": {
                "raw_score": raw.get("kyc_raw_score"),
                "weighted_score": raw.get("kyc_weighted_score"),
                "weight": 0.20,
            },
            "purpose_and_nature": {
                "raw_score": raw.get("purpose_raw_score"),
                "weighted_score": raw.get("purpose_weighted_score"),
                "weight": 0.10,
            },
            "products_and_channels": {
                "raw_score": raw.get("product_raw_score"),
                "weighted_score": raw.get("product_weighted_score"),
                "weight": 0.10,
            },
            "aml_transaction_monitoring": {
                "raw_score": raw.get("behavioral_raw_score"),
                "weighted_score": raw.get("behavioral_weighted_score"),
                "weight": 0.30,
            },
            "behavioral_transaction_monitoring": {
                "raw_score": raw.get("behavioral_raw_score"),
                "weighted_score": raw.get("behavioral_weighted_score"),
                "weight": 0.30,
            },
            "fraud_risk_telemetry": {
                "raw_score": raw.get("fraud_raw_score"),
                "weighted_score": raw.get("fraud_weighted_score"),
                "weight": 0.30,
            },
        },
        "alert_metrics": {
            "aml_alert_count": raw.get("alert_count"),
            "highest_aml_severity": raw.get("highest_alert_severity"),
            "fraud_alert_count": raw.get("fraud_alert_count"),
            "highest_fraud_severity": raw.get("highest_fraud_severity"),
        },
        "recommended_action": raw.get("recommended_action"),
        "action_checklist": checklist,
        "executive_summary": raw.get("executive_summary"),
    }


def get_alert_feed(
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    limit: int = 20
) -> list[dict[str, Any]]:
    """Retrieve open alerts from the compliance triage queue to trigger investigations.

    Args:
        severity: Filter by alert severity ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW').
        alert_type: Filter by typology domain ('AML' or 'FRAUD').
        limit: Maximum number of alerts to return (default: 20).

    Returns:
        List of priority alerts with customer identifiers and trigger rationales.
    """
    db_mgr = get_db_manager()
    return db_mgr.get_open_alerts(severity=severity, alert_type=alert_type, limit=limit)


# --------------------------------------------------------------------------
# Tool Registries
# --------------------------------------------------------------------------

CUSTOMER_TOOLS = [
    list_customers,
    get_customer_profile,
    get_expected_activity,
    get_kyc_dossier,
    get_digital_telemetry,
]

TRANSACTION_TOOLS = [
    get_transactions,
    analyze_transactions,
    get_expected_activity,
    get_transaction_alerts,
]

FRAUD_TOOLS = [
    get_fraud_alerts,
    get_digital_telemetry,
    get_transactions,
    get_customer_profile,
]

OWNERSHIP_TOOLS = [
    get_ownership_structure,
    get_country_risk,
]

RISK_TOOLS = [
    get_risk_assessment,
    get_customer_profile,
    get_country_risk,
    get_ownership_structure,
]

ALERT_TRIAGE_TOOLS = [
    get_alert_feed,
    get_risk_assessment,
    get_customer_profile,
]

EXECUTIVE_SUMMARY_TOOLS = [
    get_customer_profile,
    get_risk_assessment,
    get_transaction_alerts,
    get_fraud_alerts,
    analyze_transactions,
]
