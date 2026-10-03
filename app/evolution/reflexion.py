"""Reflexion Engine for Agent Self-Correction and Root Cause Analysis.
Inspects adjudicated cases from Dialectic Debate Arbiter or Human Overrides,
clustering failure modes and diagnosing structural blindspots in existing policies.
"""

from typing import Dict, Any, Optional
import uuid
from app.evolution.models import ReflexionInsight, FailureMode
from app.orchestrator.debate import DebateOutcome, ConflictType


class ReflexionEngine:
    """Diagnoses why existing static detection rules failed or produced false positives."""

    def analyze_case_failure(
        self,
        case_id: str,
        debate_outcome: DebateOutcome,
        customer_profile: Dict[str, Any],
        transaction_findings: Dict[str, Any],
        fraud_findings: Dict[str, Any]
    ) -> ReflexionInsight:
        """Generates a deep root-cause reflection for cases where the Arbiter intervened."""
        insight_id = f"RFLX-{uuid.uuid4().hex[:6].upper()}"

        if debate_outcome.conflict_type == ConflictType.MULE_VS_COERCED_VICTIM:
            return ReflexionInsight(
                insight_id=insight_id,
                case_id=case_id,
                failure_mode=FailureMode.MISCLASSIFIED_VICTIM_AS_MULE,
                flawed_rule_id="TM-02 (Rapid Outflow Pass-Through / Money Mule)",
                root_cause_diagnosis=(
                    "Rule TM-02 evaluates fund dispersion velocity as an isolated metric without accounting for "
                    "device biometric continuity (FaceID/TouchID) or psychological manipulation indicators. "
                    "When an innocent customer is coerced under APP social engineering, rapid transfers resemble "
                    "mule smurfing, creating a severe false positive that punishes the victim instead of protecting funds."
                ),
                overlooked_signals=[
                    "Primary hardware device match (DEV-Primary)",
                    "Biometric Level 3 authentication confirmation",
                    "Atypical interaction speed and late-night session timestamp",
                    "Zero beneficiary kickback or secondary commission inflows",
                    "TypeSafe Jev Reasoner manipulation index (0.99 CRITICAL)"
                ],
                corrective_guidance=(
                    "Introduce a 'Coercion & Biometric Guard Exemption' to TM-02: If outflow velocity is elevated "
                    "BUT hardware session shows genuine biometrics and Jev Reasoner confirms social engineering duress, "
                    "reroute policy action from Criminal Prosecution SAR to Emergency Protective Escrow Intercept."
                )
            )

        elif debate_outcome.conflict_type == ConflictType.ATO_VS_FRIENDLY_FRAUD:
            return ReflexionInsight(
                insight_id=insight_id,
                case_id=case_id,
                failure_mode=FailureMode.FRIENDLY_FRAUD_ESCALATION,
                flawed_rule_id="FR-01 (Impossible Travel / Velocity Geolocation Anomaly)",
                root_cause_diagnosis=(
                    "Rule FR-01 triggers solely on IP address country hops. Cardholders utilizing commercial VPNs "
                    "or corporate privacy proxies trip false alarms despite possessing hardware security tokens "
                    "and 3DS push notification signatures."
                ),
                overlooked_signals=[
                    "Hardware security key / FIDO2 registration token",
                    "3DS Out-of-Band confirmation on primary mobile device",
                    "Absence of credential stuffing patterns across account logs"
                ],
                corrective_guidance=(
                    "Add FIDO2/3DS step-up token attenuation: Geolocation delta alerts must be suppressed or downgraded "
                    "if hardware cryptographic key signature is verified on the transaction authorization payload."
                )
            )

        else:
            return ReflexionInsight(
                insight_id=insight_id,
                case_id=case_id,
                failure_mode=FailureMode.FALSE_POSITIVE_OFFSHORE_COMMERCE,
                flawed_rule_id="TM-05C (Offshore Secrecy & Tax Haven Financial Corridor)",
                root_cause_diagnosis=(
                    "Static threshold rules fail to distinguish verified multi-generational family inheritances "
                    "or legitimate commercial trade remittances from illicit shell smurfing."
                ),
                overlooked_signals=[
                    "Documented source-of-wealth notarization",
                    "Longstanding clean account tenure (>5 years)"
                ],
                corrective_guidance=(
                    "Incorporate relationship tenure attenuation and documented purpose verified flags into offshore scoring."
                )
            )
