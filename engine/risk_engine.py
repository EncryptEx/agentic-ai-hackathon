"""Composite KYC, Transaction Monitoring, and Fraud Risk Engine (FRAML)."""

from datetime import datetime
from typing import List, Optional
from models.customer import CustomerProfile, PEPStatus, AdverseMedia, SanctionStatus
from models.transaction import Transaction
from models.risk_score import (
    CustomerRiskAssessment, RiskTier, AlertSeverity, AMLAlert, FraudAlert
)
from engine.kyc_scorer import KYCScorer
from engine.tm_detector import TransactionMonitoringDetector
from engine.fraud_detector import FraudDetector
from config.fraud_config import FRAML_PILLAR_WEIGHTS

class RiskEngine:
    """Master FRAML engine orchestrating multi-pillar KYC, AML, and Fraud risk assessments."""

    def __init__(self):
        self.kyc_scorer = KYCScorer()
        self.tm_detector = TransactionMonitoringDetector()
        self.fraud_detector = FraudDetector()

    def evaluate_customer(
        self,
        customer: CustomerProfile,
        transactions: Optional[List[Transaction]] = None
    ) -> CustomerRiskAssessment:
        """Evaluates customer and produces full explainable FRAML risk assessment."""
        if transactions is None:
            transactions = []

        # 1. Evaluate Individual Pillars
        kyc_pillar = self.kyc_scorer.score_demographic_kyc(customer)
        purpose_pillar = self.kyc_scorer.score_purpose_and_nature(customer)
        product_pillar = self.kyc_scorer.score_products_and_channels(customer)
        alerts, behavioral_pillar = self.tm_detector.analyze_transactions(customer, transactions)
        fraud_alerts, fraud_pillar = self.fraud_detector.analyze_fraud(customer, transactions)

        # Apply FRAML Weights
        kyc_pillar.weight = FRAML_PILLAR_WEIGHTS["CUSTOMER_KYC"]
        kyc_pillar.weighted_score = round(kyc_pillar.raw_score * kyc_pillar.weight, 2)

        purpose_pillar.weight = FRAML_PILLAR_WEIGHTS["PURPOSE_NATURE"]
        purpose_pillar.weighted_score = round(purpose_pillar.raw_score * purpose_pillar.weight, 2)

        product_pillar.weight = FRAML_PILLAR_WEIGHTS["PRODUCTS_CHANNELS"]
        product_pillar.weighted_score = round(product_pillar.raw_score * product_pillar.weight, 2)

        behavioral_pillar.weight = FRAML_PILLAR_WEIGHTS["AML_BEHAVIOR"]
        behavioral_pillar.weighted_score = round(behavioral_pillar.raw_score * behavioral_pillar.weight, 2)

        fraud_pillar.weight = FRAML_PILLAR_WEIGHTS["FRAUD_RISK"]
        fraud_pillar.weighted_score = round(fraud_pillar.raw_score * fraud_pillar.weight, 2)

        # 2. Compute Base Composite Score
        composite_score = (
            kyc_pillar.weighted_score +
            purpose_pillar.weighted_score +
            product_pillar.weighted_score +
            behavioral_pillar.weighted_score +
            fraud_pillar.weighted_score
        )

        # 3. Regulatory & Typology Hard Overrides
        override_applied = False
        override_reason = ""

        # AML Override 1: Confirmed Sanctions Hit
        if customer.sanction_status == SanctionStatus.CONFIRMED_HIT:
            composite_score = 100.0
            override_applied = True
            override_reason = "STATUTORY OVERRIDE: Confirmed Sanctions / Watchlist Match."

        # AML Override 2: FATF Blacklist Transaction Activity
        has_blacklist_alert = any(a.rule_id == "TM-05A" for a in alerts)
        if has_blacklist_alert and composite_score < 90.0:
            composite_score = 92.0
            override_applied = True
            override_reason = "STATUTORY OVERRIDE: Direct wire corridor to FATF Call for Action jurisdiction."

        # Fraud Override 1: Account Takeover (ATO) Confirmed
        has_ato = any(fa.rule_id == "FR-01" for fa in fraud_alerts)
        if has_ato and composite_score < 88.0:
            composite_score = 90.0
            override_applied = True
            override_reason = "FRAUD OVERRIDE: Account Takeover (ATO) & foreign proxy session detected."

        # Fraud Override 2: First-Party Bust-Out Fraud
        has_bustout = any(fa.rule_id == "FR-04" for fa in fraud_alerts)
        if has_bustout and composite_score < 88.0:
            composite_score = 89.5
            override_applied = True
            override_reason = "FRAUD OVERRIDE: First-Party Bust-Out / Deposit Kiting detected."

        # AML Override 3: Structuring / Smurfing Confirmation
        has_structuring = any(a.rule_id == "TM-01" for a in alerts)
        if has_structuring and composite_score < 75.0:
            composite_score = 78.5
            override_applied = True
            override_reason = "TYPOLOGY OVERRIDE: Currency Transaction Reporting (CTR) Structuring detected."

        # AML Override 4: Critical Pass-through Money Mule
        has_critical_tm = any(a.severity == AlertSeverity.CRITICAL for a in alerts)
        if has_critical_tm and composite_score < 85.0:
            composite_score = 86.5
            override_applied = True
            override_reason = "TYPOLOGY OVERRIDE: Critical AML typology confirmed (Mule/Structuring)."

        # Fraud Override 3: Card Testing Attack
        has_card_fraud = any(fa.rule_id == "FR-02" for fa in fraud_alerts)
        if has_card_fraud and composite_score < 75.0:
            composite_score = 76.0
            override_applied = True
            override_reason = "FRAUD OVERRIDE: Card micro-testing attack confirmed."

        # Fraud Override 4: Synthetic Identity Fraud
        has_synthetic_id = any(fa.rule_id == "FR-05" for fa in fraud_alerts)
        if has_synthetic_id and composite_score < 80.0:
            composite_score = 82.5
            override_applied = True
            override_reason = "FRAUD OVERRIDE: Synthetic Identity & burner credentials identified."

        # AML Override 5: Foreign PEP
        if customer.pep_status == PEPStatus.FOREIGN_PEP and composite_score < 65.0:
            composite_score = 68.0
            override_applied = True
            override_reason = "STATUTORY OVERRIDE: Mandatory Enhanced Due Diligence for Foreign PEP (FATF Rec. 12)."

        # AML Override 6: Adverse Media for Financial Crime
        if customer.adverse_media in [AdverseMedia.FINANCIAL_CRIME, AdverseMedia.CORRUPTION_BRIBERY, AdverseMedia.FRAUD] and composite_score < 70.0:
            composite_score = 72.5
            override_applied = True
            override_reason = f"ADVERSE MEDIA OVERRIDE: Confirmed public derogatory news for {customer.adverse_media.value}."

        composite_score = min(100.0, max(0.0, round(composite_score, 2)))

        # 4. Map to Risk Tier
        if composite_score >= 85.0:
            tier = RiskTier.CRITICAL
        elif composite_score >= 60.0:
            tier = RiskTier.HIGH
        elif composite_score >= 35.0:
            tier = RiskTier.MEDIUM
        else:
            tier = RiskTier.LOW

        # 5. Determine Highest Alert Severities
        highest_severity = None
        if alerts:
            severities = [a.severity for a in alerts]
            if AlertSeverity.CRITICAL in severities:
                highest_severity = AlertSeverity.CRITICAL
            elif AlertSeverity.HIGH in severities:
                highest_severity = AlertSeverity.HIGH
            elif AlertSeverity.MEDIUM in severities:
                highest_severity = AlertSeverity.MEDIUM
            else:
                highest_severity = AlertSeverity.LOW

        highest_fraud_sev = None
        if fraud_alerts:
            f_sevs = [fa.severity for fa in fraud_alerts]
            if AlertSeverity.CRITICAL in f_sevs:
                highest_fraud_sev = AlertSeverity.CRITICAL
            elif AlertSeverity.HIGH in f_sevs:
                highest_fraud_sev = AlertSeverity.HIGH
            elif AlertSeverity.MEDIUM in f_sevs:
                highest_fraud_sev = AlertSeverity.MEDIUM
            else:
                highest_fraud_sev = AlertSeverity.LOW

        # 6. Generate Governance Recommendations & Checklist
        recommended_action, checklist = self._generate_recommendations(
            customer, tier, alerts, fraud_alerts, override_applied
        )

        # 7. Formulate Executive Summary
        summary = self._generate_executive_summary(
            customer, tier, composite_score, kyc_pillar, behavioral_pillar,
            fraud_pillar, alerts, fraud_alerts, override_reason
        )

        return CustomerRiskAssessment(
            customer_id=customer.customer_id,
            assessment_timestamp=datetime.now().isoformat(),
            composite_score=composite_score,
            risk_tier=tier,
            kyc_pillar=kyc_pillar,
            purpose_pillar=purpose_pillar,
            product_pillar=product_pillar,
            behavioral_pillar=behavioral_pillar,
            fraud_pillar=fraud_pillar,
            alerts=alerts,
            alert_count=len(alerts),
            highest_alert_severity=highest_severity,
            fraud_alerts=fraud_alerts,
            fraud_alert_count=len(fraud_alerts),
            highest_fraud_severity=highest_fraud_sev,
            aml_score=round(behavioral_pillar.raw_score, 2),
            fraud_score=round(fraud_pillar.raw_score, 2),
            recommended_action=recommended_action,
            action_checklist=checklist,
            executive_summary=summary
        )

    def _generate_recommendations(
        self,
        customer: CustomerProfile,
        tier: RiskTier,
        alerts: List[AMLAlert],
        fraud_alerts: List[FraudAlert],
        override_applied: bool
    ) -> (str, List[str]):
        """Generates concrete operational recommendations and audit checklist."""
        checklist: List[str] = []

        # Determine Primary Action Trigger
        has_ato = any(fa.rule_id == "FR-01" for fa in fraud_alerts)
        has_card = any(fa.rule_id == "FR-02" for fa in fraud_alerts)
        has_scam = any(fa.rule_id == "FR-03" for fa in fraud_alerts)
        has_bustout = any(fa.rule_id == "FR-04" for fa in fraud_alerts)
        has_synth = any(fa.rule_id == "FR-05" for fa in fraud_alerts)

        if has_ato:
            rec_action = "IMMEDIATE_ACCOUNT_TAKEOVER_LOCKDOWN"
            checklist.append("1. 🚨 IMMEDIATE ATO LOCKDOWN: Invalidate all active mobile/web sessions and API tokens.")
            checklist.append("2. Revoke online banking password and force credential reset via Out-of-Band (OOB) SMS/Voice.")
            checklist.append("3. Outbound wire/crypto hold placed pending direct verbal customer confirmation.")
            checklist.append("4. Contact customer on verified primary phone number to confirm identity.")

        elif has_bustout:
            rec_action = "BUST_OUT_DEPOSIT_FREEZE_AND_ATM_BLOCK"
            checklist.append("1. Place administrative freeze on ledger balance.")
            checklist.append("2. Restrict ATM cash withdrawals and peer-to-peer outbound channels.")
            checklist.append("3. Issue ACH debit inquiry to Originating Depository Financial Institution (ODFI).")
            checklist.append("4. Prepare first-party fraud loss report.")

        elif has_synth:
            rec_action = "SYNTHETIC_IDENTITY_CIF_BLOCK"
            checklist.append("1. Block Customer Information File (CIF) and freeze newly opened credit lines.")
            checklist.append("2. Demand in-person branch presentation of original government ID and physical SSN/tax card.")
            checklist.append("3. Notify fraud risk consortium of synthetic identity pattern.")

        elif has_card:
            rec_action = "BLOCK_CARD_AND_INITIATE_CHARGEBACK"
            checklist.append("1. Permanently deactivate compromised payment card.")
            checklist.append("2. Automatically issue new contactless debit card with updated PAN.")
            checklist.append("3. File fraud chargeback with Visa/Mastercard network for unauthorized CNP transactions.")

        elif has_scam:
            rec_action = "APP_SCAM_INTERVENTION_AND_CALL_VICTIM"
            checklist.append("1. Place 24-hour cooling-off delay on pending outbound P2P transfers.")
            checklist.append("2. Specialist fraud agent to contact customer for scam awareness intervention.")
            checklist.append("3. Check beneficiary account against national Mule Account Watchlist.")

        elif tier == RiskTier.CRITICAL:
            rec_action = "FILE_SAR_AND_IMMEDIATE_ACCOUNT_RESTRICTION"
            checklist.append("1. Escalate file immediately to Head of Financial Crime Compliance / MLRO.")
            checklist.append("2. Implement immediate restriction on outbound payments and crypto off-ramps.")
            checklist.append("3. Draft and submit Suspicious Activity Report (SAR / STR) to national Financial Intelligence Unit (FIU).")
            checklist.append("4. Request complete transaction substantiation (invoices, source of funds evidence).")
            checklist.append("5. Convene Risk Committee to evaluate relationship termination / debanking.")

        elif tier == RiskTier.HIGH:
            rec_action = "ENHANCED_DUE_DILIGENCE_REQUIRED"
            checklist.append("1. Initiate formal Enhanced Due Diligence (EDD) review cycle.")
            checklist.append("2. Collect certified proof of Source of Wealth (tax returns, audited financials, inheritance probate).")
            if customer.pep_status != PEPStatus.NONE:
                checklist.append("3. Obtain Senior Executive / Board level approval for PEP relationship continuation.")
            checklist.append("4. Set enhanced transaction monitoring rules with lower alert thresholds for 180 days.")
            checklist.append("5. Schedule 6-month periodic KYC refresh (rather than standard 3-year cycle).")

        elif tier == RiskTier.MEDIUM:
            rec_action = "STANDARD_DUE_DILIGENCE_WITH_ANNUAL_REVIEW"
            checklist.append("1. Maintain standard ongoing transaction monitoring.")
            checklist.append("2. Schedule next periodic KYC review in 12 months.")
            checklist.append("3. Verify identity document expiration dates within next 90 days.")

        else: # LOW
            rec_action = "STANDARD_DUE_DILIGENCE_LOW_RISK"
            checklist.append("1. Customer cleared for standard retail banking operations.")
            checklist.append("2. Automated ongoing watchlist screening against sanctions updates.")
            checklist.append("3. Scheduled for regular 36-month low-risk refresh cycle.")

        # Additional alert-specific items
        if any(a.rule_id == "TM-01" for a in alerts):
            checklist.append("[AML Action TM-01]: Investigate cash deposit locations and interview branch tellers.")
        if any(a.rule_id == "TM-02" for a in alerts):
            checklist.append("[AML Action TM-02]: Review beneficiary VASP / wallet address for known illicit links via blockchain analytics.")
        if any(a.rule_id.startswith("TM-05") for a in alerts):
            checklist.append("[AML Action TM-05]: Request SWIFT MT103 full messaging logs and underlying trade contracts.")

        return rec_action, checklist

    def _generate_executive_summary(
        self,
        customer: CustomerProfile,
        tier: RiskTier,
        composite_score: float,
        kyc_pillar,
        behavioral_pillar,
        fraud_pillar,
        alerts: List[AMLAlert],
        fraud_alerts: List[FraudAlert],
        override_reason: str
    ) -> str:
        """Synthesizes an executive compliance summary combining KYC, AML, and Fraud."""
        parts = [
            f"Customer {customer.first_name} {customer.last_name} ({customer.customer_id}) "
            f"assessed at Risk Tier: {tier.value} (Composite Score: {composite_score}/100)."
        ]

        if override_reason:
            parts.append(f"**{override_reason}**")

        parts.append(
            f"KYC pillar scored {kyc_pillar.raw_score:.1f}/100 "
            f"(Citizenship: {customer.citizenship}, Residence: {customer.residence_country}, "
            f"PEP: {customer.pep_status.value}, Occupation: {customer.occupation})."
        )

        if fraud_alerts:
            fraud_names = ", ".join([f"{fa.rule_name} ({fa.severity.value})" for fa in fraud_alerts])
            parts.append(
                f"Fraud detection flagged {len(fraud_alerts)} alert(s) pushing Fraud risk to "
                f"{fraud_pillar.raw_score:.1f}/100. Triggered fraud rules: {fraud_names}."
            )
        else:
            parts.append(f"Fraud & digital identity risk scored clean at {fraud_pillar.raw_score:.1f}/100.")

        if alerts:
            alert_names = ", ".join([f"{a.rule_name} ({a.severity.value})" for a in alerts])
            parts.append(
                f"AML Transaction monitoring triggered {len(alerts)} alert(s) pushing AML behavioral risk to "
                f"{behavioral_pillar.raw_score:.1f}/100. Triggered rules: {alert_names}."
            )
        else:
            parts.append("AML transaction monitoring history is clean with zero typology breaches.")

        return " ".join(parts)
