"""Alert Feed & Automated Agent Triage Dispatcher.

Bridges the detection engine (Pillars 4 & 5 alerts) and the Google ADK
multi-agent investigation pipeline.

Workflow:
1. Fetch highest-severity open alerts from `storage.database.DatabaseManager`.
2. Format alert case packets (Customer ID, triggering rule, evidence IDs).
3. Dispatch to the multi-agent investigation pipeline.
4. Persist the generated investigation dossier back into the database.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.agent import root_agent
from storage.database import DatabaseManager, DEFAULT_DB_PATH


class AlertDispatcher:
    """Dispatches compliance alerts to the AI investigation team."""

    def __init__(self, db_mgr: Optional[DatabaseManager] = None):
        self.db = db_mgr or DatabaseManager(DEFAULT_DB_PATH)

    def get_pending_queue(
        self,
        severity: Optional[str] = "CRITICAL",
        alert_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Fetch open alerts ranked by urgency to be investigated."""
        return self.db.get_open_alerts(severity=severity, alert_type=alert_type, limit=limit)

    def prepare_case_packet(self, customer_id: str, alert_id: Optional[str] = None) -> Dict[str, Any]:
        """Prepares a full case dossier packet for agent invocation."""
        cust_360 = self.db.get_customer_360(customer_id)
        if not cust_360:
            raise ValueError(f"Customer {customer_id!r} not found in database.")

        trigger_alert = None
        if alert_id:
            all_alerts = cust_360.get("alerts", []) + cust_360.get("fraud_alerts", [])
            trigger_alert = next((a for a in all_alerts if a.get("alert_id") == alert_id), None)

        return {
            "customer_id": customer_id,
            "customer_name": f"{cust_360['customer'].get('first_name', '')} {cust_360['customer'].get('last_name', '')}".strip(),
            "archetype": cust_360["customer"].get("archetype"),
            "risk_tier": cust_360["assessment"].get("risk_tier") if cust_360.get("assessment") else "UNKNOWN",
            "composite_score": cust_360["assessment"].get("composite_score") if cust_360.get("assessment") else 0.0,
            "trigger_alert": trigger_alert,
            "open_alert_count": len(cust_360.get("alerts", [])) + len(cust_360.get("fraud_alerts", [])),
        }

    def generate_investigation_prompt(self, customer_id: str, trigger_alert: Optional[Dict[str, Any]] = None) -> str:
        """Constructs an initial prompt directing the multi-agent team."""
        if trigger_alert:
            rule_id = trigger_alert.get("rule_id", "ANOMALY")
            rule_name = trigger_alert.get("rule_name", "Transaction Anomaly")
            severity = trigger_alert.get("severity", "HIGH")
            summary = trigger_alert.get("summary", "Unusual account activity detected.")
            return (
                f"Please conduct an immediate financial crime investigation on customer '{customer_id}'. "
                f"This case was triggered by [{severity}] alert {rule_id}: {rule_name} ('{summary}'). "
                f"Evaluate customer identity, full transaction history, fraud and digital telemetry, "
                f"ownership connections, and composite FRAML risk indicators before preparing the final "
                f"11-section investigative report."
            )
        return (
            f"Please conduct a comprehensive financial crime and FRAML investigation on customer '{customer_id}'. "
            f"Review all KYC CDD attributes, transaction velocity, cyber/fraud telemetry, and multi-pillar risk "
            f"scores to produce the final 11-section investigative dossier."
        )

    def mark_alert_investigated(self, alert_id: str, notes: str = ""):
        """Marks an alert as investigated."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE alerts SET status = 'INVESTIGATED' WHERE alert_id = ?",
                (alert_id,)
            )
            conn.commit()


def generate_specialist_investigation_report(
    customer_id: str,
    trigger_alert: Optional[Dict[str, Any]] = None
) -> str:
    """Synthesize findings from all five specialist tools into a consolidated 11-section FRAML investigation report."""
    from app.tools import (
        analyze_transactions,
        get_country_risk,
        get_customer_profile,
        get_digital_telemetry,
        get_expected_activity,
        get_fraud_alerts,
        get_kyc_dossier,
        get_ownership_structure,
        get_risk_assessment,
        get_transaction_alerts,
        get_transactions,
    )

    profile = get_customer_profile(customer_id)
    if "error" in profile:
        return f"Error: Customer {customer_id!r} could not be retrieved from the compliance database."

    kyc = get_kyc_dossier(customer_id)
    tx_analysis = analyze_transactions(customer_id)
    tx_alerts = get_transaction_alerts(customer_id)
    fraud_alerts = get_fraud_alerts(customer_id)
    telemetry = get_digital_telemetry(customer_id)
    ownership = get_ownership_structure(customer_id)
    risk = get_risk_assessment(customer_id)
    txs = get_transactions(customer_id)

    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or profile.get('name', 'Unknown')
    archetype = profile.get("archetype", "RETAIL_INDIVIDUAL")
    country = profile.get("residence_country") or profile.get("country", "US")
    tier = risk.get("risk_tier", "MEDIUM") if "error" not in risk else "UNKNOWN"
    comp_score = risk.get("composite_score", 0.0) if "error" not in risk else 0.0
    sub_scores = risk.get("sub_scores", {}) if "error" not in risk else {}
    aml_score = sub_scores.get("aml_score", 0.0)
    fraud_score = sub_scores.get("fraud_score", 0.0)
    directive = risk.get("recommended_action", "MANUAL_COMPLIANCE_REVIEW") if "error" not in risk else "REVIEW"
    checklist = risk.get("action_checklist", []) if "error" not in risk else []

    # Typologies identified
    typologies = []
    for a in tx_alerts:
        typologies.append(f"{a.get('rule_id')}: {a.get('rule_name')}")
    for f in fraud_alerts:
        typologies.append(f"{f.get('rule_id')}: {f.get('rule_name')}")
    if not typologies:
        typologies = ["Standard Baseline Activity (No Breaches)"]

    # Trigger rationale
    if trigger_alert:
        trigger_desc = f"Triggered by [{trigger_alert.get('severity', 'HIGH')}] {trigger_alert.get('rule_id')}: {trigger_alert.get('rule_name')} - {trigger_alert.get('summary')}"
    elif typologies and typologies[0] != "Standard Baseline Activity (No Breaches)":
        trigger_desc = f"Triggered by {len(tx_alerts)} AML monitoring alert(s) and {len(fraud_alerts)} fraud alert(s). Highest priority: {typologies[0]}"
    else:
        trigger_desc = "Routine Periodic Compliance Review & FRAML Risk Assessment."

    # Inbound / Outbound totals
    inbound_amt = sum(t["amount_usd"] for t in txs if t.get("direction") == "INBOUND")
    outbound_amt = sum(t["amount_usd"] for t in txs if t.get("direction") == "OUTBOUND")
    total_vol = tx_analysis.get("total_volume", sum(t["amount_usd"] for t in txs))

    # Devices and IPs
    sess_tel = telemetry.get("session_and_device_telemetry", {})
    devices = sess_tel.get("devices_observed", [])
    ips = sess_tel.get("ips_observed", [])

    pep_details = profile.get("pep_details")
    pep_info = f" ({pep_details})" if pep_details else ""
    media_details = profile.get("adverse_media_details")
    media_info = f" ({media_details})" if media_details else ""
    sanction_details = profile.get("sanction_details")
    sanction_info = f" ({sanction_details})" if sanction_details else ""

    products_held = profile.get("products_held", [])
    products_str = ", ".join(products_held) if isinstance(products_held, list) else str(products_held or "CURRENT_ACCOUNT")

    divergence_obs = "Severe velocity and volume deviation from stated retail profile." if tx_analysis.get("flags") else "Account behavior remains consistent with onboarding baseline."
    cyber_obs = "Multi-device or proxy access detected indicating potential credential compromise or synthetic fabrication." if (len(devices) > 1 or fraud_alerts) else "Device and session telemetry align with primary registered footprint."

    # Format 11 sections
    report = f"""# FINANCIAL CRIME & FRAML INVESTIGATION DOSSIER
**CONFIDENTIAL // REGULATORY & COMPLIANCE INTERNAL WORKING PAPER**

---

### 1. Case Overview
* **Case Identifier:** CASE-{customer_id}
* **Subject Under Review:** {name} (ID: `{customer_id}`) | Archetype: `{archetype}`
* **Jurisdiction:** Citizenship: {profile.get('citizenship', 'N/A')} | Residence: {country} | Tax: {profile.get('tax_residence_country', 'N/A')}
* **Investigation Trigger / Rationale:** {trigger_desc}
* **Investigation Scope & Timeline:** {len(txs)} transactions examined across history, aggregating ${total_vol:,.2f} USD gross turnover (${inbound_amt:,.2f} inbound / ${outbound_amt:,.2f} outbound).
* **Primary Typologies Identified:** {", ".join(typologies)}
* **Case Classification & Priority:** **{tier} RISK** (Composite FRAML Score: **{comp_score:.1f}/100**)
* **Executive Synopsis:** Customer {name} presents an evaluated FRAML risk score of {comp_score:.1f}/100 ({tier} tier) with an AML sub-score of {aml_score:.1f} and Fraud sub-score of {fraud_score:.1f}. Active surveillance flagged {len(tx_alerts)} AML transaction monitoring alerts and {len(fraud_alerts)} cybercrime/fraud anomalies. Governance directive requires `{directive}`.

---

### 2. Customer Overview
* **Demographics & Onboarding:** {name}, age {profile.get('age', 'N/A')}, onboarded via `{profile.get('onboarding_channel', 'DIGITAL')}` on {profile.get('onboarding_date', 'N/A')}. Products held: {products_str}.
* **Occupation & Economic Profile:** Employed as {profile.get('occupation', 'N/A')} at {profile.get('employer_name', 'N/A')} (Industry: {profile.get('industry', 'N/A')}).
* **Wealth & Income Plausibility:**
  - Declared Annual Income: ${profile.get('annual_income_usd', 0):,.2f} USD | Net Worth: ${profile.get('net_worth_usd', 0):,.2f} USD
  - Declared Expected Monthly Turnover: ${profile.get('declared_expected_monthly_turnover_usd', 0):,.2f} USD
  - Declared Max Single Transaction: ${profile.get('declared_expected_max_single_tx_usd', 0):,.2f} USD
  - Source of Funds: {profile.get('source_of_funds', 'N/A')} | Source of Wealth: {profile.get('source_of_wealth', 'N/A')}
* **Watchlist & Statutory Screening:**
  - PEP Status: **{profile.get('pep_status', 'NONE')}**{pep_info}
  - Adverse Media: **{profile.get('adverse_media', 'NONE')}**{media_info}
  - Sanctions Screening: **{profile.get('sanction_status', 'CLEAN')}**{sanction_info}
* **Digital Identity Footprint:**
  - Email: `{profile.get('email_address', 'N/A')}` ({profile.get('email_domain_type', 'STANDARD')})
  - Phone: `{profile.get('phone_number', 'N/A')}` ({profile.get('phone_line_type', 'MOBILE')})
  - Synthetic Identity Anomaly Index: **{profile.get('synthetic_identity_score', 0):.1f}/100**

---

### 3. Key Observations
* **Cross-Pillar Divergence:** {divergence_obs}
* **Behavioral Thresholds:** {len(tx_analysis.get("flags", []))} behavioral anomaly flags detected by Transaction Monitoring engine.
* **Cyber Forensics:** {cyber_obs}

---

### 4. Transaction Patterns & AML Monitoring
* **Gross Turnover:** ${total_vol:,.2f} USD across {tx_analysis.get('transaction_count', len(txs))} transactions ({tx_analysis.get('deposit_count', 0)} inbound, {tx_analysis.get('outbound_count', 0)} outbound).
* **Cash Activity:** {tx_analysis.get('cash_count', 0)} cash transactions recorded. Near-CTR-threshold ($7,500-$9,999) deposits: {tx_analysis.get('near_threshold_deposits', 0)}.
* **Triggered AML Monitoring Alerts ({len(tx_alerts)}):**
"""
    if tx_alerts:
        for a in tx_alerts:
            report += f"  - **[{a.get('rule_id')}] {a.get('rule_name')}** ({a.get('severity')} Severity | Impact: +{a.get('score_impact', 0):.1f})\n    *Summary:* {a.get('summary')}\n    *Supporting Tx IDs:* {', '.join(a.get('supporting_transaction_ids', []))}\n"
    else:
        report += "  - Zero AML transaction monitoring rules breached.\n"

    report += f"""
---

### 5. Fraud & Cybercrime Telemetry Findings
* **Active Fraud Alerts ({len(fraud_alerts)}):**
"""
    if fraud_alerts:
        for f in fraud_alerts:
            report += f"  - **[{f.get('rule_id')}] {f.get('rule_name')}** ({f.get('severity')} Severity | Impact: +{f.get('score_impact', 0):.1f})\n    *Forensic Summary:* {f.get('summary')}\n    *Supporting Tx IDs:* {', '.join(f.get('supporting_transaction_ids', []))}\n"
    else:
        report += "  - Zero active fraud or cybercrime attack alerts.\n"

    report += f"""* **Device & Session Telemetry:**
  - Primary Registered Device: `{profile.get('device_primary_id', 'N/A')}`
  - Observed Devices: {', '.join(devices) if devices else 'None'} ({len(devices)} unique)
  - Observed IP Addresses: {', '.join(ips) if ips else 'None'} (Primary Country: {profile.get('primary_ip_country', 'N/A')})
  - Declined Authorization Attempts: {sess_tel.get('declined_auth_attempts', 0)}
  - Rapid New Payee Transfers: {sess_tel.get('new_payee_transfers', 0)}
* **Fraud Verdict:** {"ACCOUNT COMPROMISED / SUSPECTED TAKEOVER (Hostile foreign session & draining wire)." if any('ATO' in a.get('rule_id', '') or 'ATO' in a.get('rule_name', '') for a in fraud_alerts) else "MALICIOUS SYNTHETIC / FIRST-PARTY RISK" if profile.get('synthetic_identity_score', 0) > 60 else "No active cyber-fraud threat."}

---

### 6. Ownership & Control Findings
* **Beneficial Ownership (UBOs):**
"""
    shareholders = ownership.get("shareholders", [])
    if shareholders:
        for s in shareholders:
            report += f"  - Entity: **{s.get('entity')}** ({s.get('country')}) — Equity Stake: {s.get('stake', 0)*100:.0f}% ({s.get('note', 'Beneficial owner')})\n"
    else:
        report += "  - Standard individual retail direct ownership (100% self-owned).\n"

    directors = ownership.get("directors", [])
    if directors:
        report += "* **Executive Control & Directorships:**\n"
        for d in directors:
            report += f"  - {d.get('entity')} ({d.get('country')}) — Role: {d.get('role')} ({d.get('note', '')})\n"

    report += f"""* **Jurisdiction Risk Assessment:**
  - Residence Country: {country} — Risk Rating: {get_country_risk(country).get('rating', 'LOW').upper()}
  - Citizenship: {profile.get('citizenship', 'US')} — Risk Rating: {get_country_risk(profile.get('citizenship', 'US')).get('rating', 'LOW').upper()}

---

### 7. Relevant Risk Indicators & FRAML Score
* **Composite FRAML Score:** **{comp_score:.1f} / 100** ({tier} TIER)
* **Domain Sub-Scores:**
  - AML Risk Sub-Score: **{aml_score:.1f} / 100**
  - Fraud & Cyber Risk Sub-Score: **{fraud_score:.1f} / 100**
* **5-Pillar Risk Engine Breakdown:**
"""
    pillars = risk.get("pillars", {})
    if pillars:
        p1 = pillars.get("kyc_demographics", {})
        p2 = pillars.get("purpose_and_nature", {})
        p3 = pillars.get("products_and_channels", {})
        p4 = pillars.get("aml_transaction_monitoring", {}) or pillars.get("behavioral_transaction_monitoring", {})
        p5 = pillars.get("fraud_risk_telemetry", {})
        report += f"  - **Pillar 1 (Customer KYC & Demographics - 20%):** Raw: {p1.get('raw_score', 0):.1f}/100 | Weighted: {p1.get('weighted_score', 0):.2f}\n"
        report += f"  - **Pillar 2 (Purpose & Relationship Nature - 10%):** Raw: {p2.get('raw_score', 0):.1f}/100 | Weighted: {p2.get('weighted_score', 0):.2f}\n"
        report += f"  - **Pillar 3 (Products & Channels - 10%):** Raw: {p3.get('raw_score', 0):.1f}/100 | Weighted: {p3.get('weighted_score', 0):.2f}\n"
        report += f"  - **Pillar 4 (AML Transaction Monitoring - 30%):** Raw: {p4.get('raw_score', 0):.1f}/100 | Weighted: {p4.get('weighted_score', 0):.2f}\n"
        report += f"  - **Pillar 5 (Fraud Risk & Digital Telemetry - 30%):** Raw: {p5.get('raw_score', 0):.1f}/100 | Weighted: {p5.get('weighted_score', 0):.2f}\n"

    report += f"""* **Governance Directive:** `{directive}`

---

### 8. Evidence Supporting Each Finding
"""
    high_impact_txs = [t for t in txs if t.get("is_fraud_synthetic") or t.get("is_suspicious_synthetic") or t.get("amount_usd", 0) > 7500][:6]
    if high_impact_txs:
        for t in high_impact_txs:
            flag_info = f"[{t.get('fraud_typology_tag') or t.get('synthetic_typology_tag') or 'HIGH_VALUE'}]"
            report += f"- **Tx `{t.get('transaction_id')}`** ({t.get('timestamp')[:10]}): {t.get('direction')} ${t.get('amount_usd', 0):,.2f} via {t.get('channel')} to/from '{t.get('counterparty_name')}' ({t.get('counterparty_country')}) | Device: `{t.get('device_id', 'N/A')}` | Auth: `{t.get('auth_status', 'AUTHORIZED')}` {flag_info}\n"
    else:
        report += "- All evaluated transactions align with standard low-risk retail banking parameters.\n"

    report += f"""
---

### 9. Contradictory or Mitigating Evidence
* {"Customer possesses established banking relationship with no past sanctions or criminal convictions." if profile.get('sanction_status') == 'CLEAN' and profile.get('adverse_media') == 'NONE' else "Derogatory screening findings present with no mitigating explanations identified."}
* {"No unauthorized session disputes filed prior to trigger incident." if fraud_alerts else "Clean behavioral record across digital channel logins."}

---

### 10. Missing Information
* Verification of source of wealth documentation for transaction clusters exceeding declared expected income.
* Direct customer callback and out-of-band biometric verification to confirm device authorization.
* Confirmation of beneficial ownership for third-party commercial counterparties.

---

### 11. Suggested Next Investigative Questions & Action Checklist
"""
    if checklist:
        for item in checklist:
            report += f"- [ ] **Action:** {item}\n"
    else:
        report += "- [ ] Complete standard periodic customer due diligence refresh.\n"

    report += f"""
---

### Overall Case Summary & Governance Disposition
**Decision-Support Recommendation:** Based on multi-specialist investigation across KYC CDD, ledger transactions, device telemetry, and 5-pillar risk evaluation, this case is assigned **{tier} PRIORITY**. The compliance officer should immediately execute **`{directive}`** and follow the Operational Action Checklist.

*DISCLAIMER: All entities, transactions, device telemetry, and risk scores in this case dossier are 100% SYNTHETIC and fictional. This multi-agent system provides decision-support analysis for human compliance officers; it does not make autonomous legal, SAR-filing, or debanking decisions.*
"""
    return report.strip()


def generate_executive_summary_report(
    customer_id: str,
    trigger_alert: Optional[Dict[str, Any]] = None
) -> str:
    """Synthesize findings from specialist tools into a concise, decision-ready Executive Summary for human compliance officers."""
    from app.tools import (
        analyze_transactions,
        get_customer_profile,
        get_digital_telemetry,
        get_fraud_alerts,
        get_risk_assessment,
        get_transaction_alerts,
        get_transactions,
    )

    profile = get_customer_profile(customer_id)
    if "error" in profile:
        return f"Error: Customer {customer_id!r} could not be retrieved from the compliance database."

    risk = get_risk_assessment(customer_id)
    tx_analysis = analyze_transactions(customer_id)
    tx_alerts = get_transaction_alerts(customer_id)
    fraud_alerts = get_fraud_alerts(customer_id)
    telemetry = get_digital_telemetry(customer_id)
    txs = get_transactions(customer_id)

    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or profile.get('name', 'Unknown')
    archetype = profile.get("archetype", "RETAIL_INDIVIDUAL")
    country = profile.get("residence_country") or profile.get("country", "US")
    tier = risk.get("risk_tier", "MEDIUM") if "error" not in risk else "UNKNOWN"
    comp_score = risk.get("composite_score", 0.0) if "error" not in risk else 0.0
    sub_scores = risk.get("sub_scores", {}) if "error" not in risk else {}
    aml_score = sub_scores.get("aml_score", 0.0)
    fraud_score = sub_scores.get("fraud_score", 0.0)
    directive = risk.get("recommended_action", "MANUAL_COMPLIANCE_REVIEW") if "error" not in risk else "REVIEW"
    checklist = risk.get("action_checklist", []) if "error" not in risk else []

    # Typologies identified
    typologies = []
    for a in tx_alerts:
        typologies.append(f"{a.get('rule_id')}: {a.get('rule_name')}")
    for f in fraud_alerts:
        typologies.append(f"{f.get('rule_id')}: {f.get('rule_name')}")

    # Trigger rationale
    if trigger_alert:
        trigger_desc = f"[{trigger_alert.get('severity', 'HIGH')}] {trigger_alert.get('rule_id')}: {trigger_alert.get('rule_name')} - {trigger_alert.get('summary')}"
    elif typologies:
        trigger_desc = f"{len(tx_alerts)} AML alert(s) and {len(fraud_alerts)} fraud alert(s). Lead alert: {typologies[0]}"
    else:
        trigger_desc = "Routine Periodic FRAML Compliance Review"

    # Transaction financials
    inbound_amt = sum(t["amount_usd"] for t in txs if t.get("direction") == "INBOUND")
    outbound_amt = sum(t["amount_usd"] for t in txs if t.get("direction") == "OUTBOUND")
    total_vol = tx_analysis.get("total_volume", sum(t["amount_usd"] for t in txs))

    # Calculate suspicious / at-risk volume
    near_thresh = tx_analysis.get("near_threshold_deposits", 0)
    cash_cnt = tx_analysis.get("cash_count", 0)
    suspicious_vol = 0.0
    flagged_tx_ids = set()
    for a in tx_alerts + fraud_alerts:
        for tid in a.get("supporting_transaction_ids", []):
            flagged_tx_ids.add(tid)
    if flagged_tx_ids:
        suspicious_vol = sum(t["amount_usd"] for t in txs if t.get("transaction_id") in flagged_tx_ids)
    if suspicious_vol == 0.0 and (tx_alerts or fraud_alerts):
        suspicious_vol = outbound_amt if outbound_amt > 0 else total_vol * 0.5

    # Craft Bottom Line Up Front (BLUF)
    if tier in ("CRITICAL", "HIGH"):
        top_cause = typologies[0] if typologies else "elevated behavioral anomalies"
        bluf = (
            f"**URGENT ESCALATION REQUIRED:** Customer {name} ({customer_id}) presents a **{tier}** FRAML risk profile "
            f"(Composite Score: **{comp_score:.1f}/100**). Active typologies indicate severe exposure driven by **{top_cause}**. "
            f"Immediate operational execution of **`{directive}`** is advised."
        )
    elif tier == "MEDIUM":
        bluf = (
            f"**ELEVATED RISK REVIEW:** Customer {name} ({customer_id}) exhibits moderate FRAML risk "
            f"(Composite Score: **{comp_score:.1f}/100**). Identified behavioral anomalies warrant Enhanced Due Diligence (EDD) "
            f"and supervisory review under directive **`{directive}`**."
        )
    else:
        bluf = (
            f"**ROUTINE COMPLIANCE BASELINE:** Customer {name} ({customer_id}) presents low overall risk "
            f"(Composite Score: **{comp_score:.1f}/100**). No immediate restrictive measures or SAR filings are warranted at this time."
        )

    # Top red flags (3-4 points)
    red_flags = []
    if tx_alerts:
        for a in tx_alerts[:2]:
            red_flags.append(f"**AML / Transaction Monitoring:** Triggered `{a.get('rule_id')}` ({a.get('rule_name')}) — {a.get('summary')}")
    if fraud_alerts:
        for f in fraud_alerts[:2]:
            red_flags.append(f"**Fraud & Cyber Telemetry:** Triggered `{f.get('rule_id')}` ({f.get('rule_name')}) — {f.get('summary')}")
    if profile.get("pep_status") not in (None, "NONE", "NO"):
        red_flags.append(f"**PEP Exposure:** Confirmed Politically Exposed Person: {profile.get('pep_details') or profile.get('pep_status')}")
    if profile.get("sanction_status") not in (None, "CLEAN", "NO", "NONE"):
        red_flags.append(f"**Sanctions Match:** Derogatory screening hit: {profile.get('sanction_details') or profile.get('sanction_status')}")
    if profile.get("adverse_media") not in (None, "CLEAN", "NO", "NONE"):
        red_flags.append(f"**Adverse Media:** Derogatory media hit: {profile.get('adverse_media_details') or profile.get('adverse_media')}")
    if not red_flags:
        red_flags.append("No active statutory overrides or critical alerts triggered; profile aligns with expected baseline.")

    # Overrides
    overrides_text = "None applied"
    if tier in ("CRITICAL", "HIGH") and (tx_alerts or fraud_alerts):
        applied = [t for t in typologies[:3]]
        overrides_text = f"High-risk overrides applied: {', '.join(applied)}"

    # Executive Summary Markdown
    summary = f"""# ⚡ EXECUTIVE BRIEFING // FINANCIAL CRIME INVESTIGATION
**CONFIDENTIAL // DECISION BRIEFING FOR COMPLIANCE LEADERSHIP**

---

### 1. Bottom Line Up Front (BLUF)
{bluf}

---

### 2. Case & Subject Snapshot
* **Case Identifier:** `CASE-{customer_id}`
* **Subject Under Review:** **{name}** (ID: `{customer_id}`) | Archetype: `{archetype}`
* **Jurisdiction:** {country} (Citizenship: {profile.get('citizenship', 'N/A')})
* **Investigation Trigger:** {trigger_desc}
* **Investigation Scope:** {len(txs)} transactions scrutinized totaling **${total_vol:,.2f} USD**

---

### 3. FRAML Risk Profile & Scores
* **Composite FRAML Score:** **{comp_score:.1f} / 100** — **[{tier}]** Risk Tier
* **AML Behavioral Sub-Score:** **{aml_score:.1f} / 100**
* **Fraud & Cyber Sub-Score:** **{fraud_score:.1f} / 100**
* **Statutory / Policy Overrides:** {overrides_text}

---

### 4. Critical Red Flags & Primary Typologies
"""
    for flag in red_flags:
        summary += f"- {flag}\n"

    summary += f"""
---

### 5. Financial Exposure & Impact
* **Total Scrutinized Turnover:** **${total_vol:,.2f} USD** ({len(txs)} transactions)
* **Inbound Capital:** ${inbound_amt:,.2f} USD | **Outbound Dispersal:** ${outbound_amt:,.2f} USD
* **Suspected At-Risk / Flagged Volume:** **${suspicious_vol:,.2f} USD**
* **Cash & Near-Threshold Volume:** {cash_cnt} cash transactions | {near_thresh} near-CTR deposits ($7,500-$9,999)

---

### 6. Immediate Recommended Action
* **Primary Compliance Directive:** **`{directive}`**
* **Immediate Operational Checklist:**
"""
    if checklist:
        for item in checklist[:3]:
            summary += f"  - [ ] **Action:** {item}\n"
    else:
        summary += "  - [ ] Complete standard periodic compliance review.\n"

    summary += f"""
---

### 7. Human Governance & Compliance Authority
* **Human-in-the-Loop Authority:** *This executive summary provides automated decision-support intelligence for a human investigator. Final decisions regarding SAR filings, account freezes, or regulatory notices remain the sole responsibility of authorized human compliance officers.*
* **Synthetic Data Disclaimer:** *ALL DATA IS SYNTHETIC AND FICTIONAL. Entities, account numbers, and activities are synthetic constructs created for compliance demonstration.*
"""
    return summary.strip()


