"""Policy Optimizer for Dynamic Rule Evolution.
Synthesizes mutated rule definitions, threshold calibrations, and exemption guards based on Reflexion insights.
"""

from typing import Dict, Any
import uuid
from app.evolution.models import PolicyMutation, ReflexionInsight, FailureMode


class PolicyOptimizer:
    """Mutates detection rules and synthesizes production-ready DSL policy patches."""

    def evolve_policy_rule(self, reflexion: ReflexionInsight) -> PolicyMutation:
        mutation_id = f"MUT-{uuid.uuid4().hex[:6].upper()}"

        if reflexion.failure_mode == FailureMode.MISCLASSIFIED_VICTIM_AS_MULE:
            return PolicyMutation(
                mutation_id=mutation_id,
                target_rule_id="TM-02",
                version_tag="v2.1-coercion-guarded",
                previous_condition_dsl="""WHEN funds_outflow_velocity >= 3.0x AND recipient_is_new == TRUE 
THEN TRIGGER_ALERT('TM-02', SEVERITY='CRITICAL', ACTION='CRIMINAL_SAR_DEBANK')""",
                evolved_condition_dsl="""WHEN funds_outflow_velocity >= 3.0x AND recipient_is_new == TRUE
EXCEPT WHEN (
    hardware_device.is_primary_device == TRUE 
    AND biometric_auth_level >= 'LEVEL_3_BIOMETRIC'
    AND jev_assessment.manipulation_indicators == TRUE
    AND transaction.has_syndicate_kickback == FALSE
)
THEN TRIGGER_POLICY_OVERRIDE(
    ACTION='PROTECTIVE_ESCROW_HOLD',
    NOTIFY='APP_SCAM_VICTIM_INTERVENTION_TEAM',
    SUPPRESS_RULES=['TM-02_CRIMINAL_DEBANK']
)""",
                parameter_adjustments={
                    "outflow_velocity_threshold": 3.0,
                    "biometric_confidence_min": 0.90,
                    "jev_coercion_score_min": 0.85,
                    "cooling_off_hold_hours": 24
                },
                exemption_guards=[
                    "GUARD_BIOMETRIC_CONTINUITY: Verified TouchID/FaceID eliminates credential stuffing or burner mule hypothesis",
                    "GUARD_JEV_COERCION_AFFIRMATION: Confirmed psychological duress switches intent from accomplice to victim",
                    "GUARD_ZERO_KICKBACK: Absence of secondary intermediary transaction splits"
                ],
                mutation_rationale=(
                    "Guards TM-02 against mischaracterizing elderly or vulnerable victims of social engineering scams as "
                    "syndicate money mules. Preserves severe mule triggers for unverified burner devices while protecting genuine customers."
                )
            )

        elif reflexion.failure_mode == FailureMode.FRIENDLY_FRAUD_ESCALATION:
            return PolicyMutation(
                mutation_id=mutation_id,
                target_rule_id="FR-01",
                version_tag="v2.1-fido2-stepup",
                previous_condition_dsl="""WHEN ip_geo_distance_speed >= 800km/h THEN TRIGGER_ALERT('FR-01', ACTION='FORCE_FREEZE')""",
                evolved_condition_dsl="""WHEN ip_geo_distance_speed >= 800km/h 
EXCEPT WHEN (hardware_fido2_token_present == TRUE AND user_agent_device_fingerprint_match == TRUE)
THEN DOWNGRADE_TO_STEPUP_CHALLENGE(CHALLENGE='3DS_PUSH_APP', REASON='SUSPECTED_VPN_ROUTING')""",
                parameter_adjustments={
                    "geo_velocity_threshold_kmh": 850,
                    "fido2_trust_factor": 0.95
                },
                exemption_guards=[
                    "GUARD_FIDO2_CRYPTOGRAPHIC_TOKEN: Physical security key cannot be spoofed across VPN endpoints"
                ],
                mutation_rationale="Prevents legitimate VPN users from suffering disruptive false-positive account freezes."
            )

        else:
            return PolicyMutation(
                mutation_id=mutation_id,
                target_rule_id="TM-05C",
                version_tag="v2.1-tenure-discount",
                previous_condition_dsl="""WHEN counterparty_country IN ('TAX_HAVEN_LIST') THEN TRIGGER_ALERT('TM-05C')""",
                evolved_condition_dsl="""WHEN counterparty_country IN ('TAX_HAVEN_LIST')
EXCEPT WHEN (customer_tenure_years >= 5.0 AND kyc_source_of_wealth_verified == TRUE)
THEN CLASSIFY_AS('ROUTINE_DOCUMENTED_PRIVATE_REMITTANCE')""",
                parameter_adjustments={
                    "minimum_tenure_years": 5.0,
                    "wealth_doc_validity_days": 365
                },
                exemption_guards=[
                    "GUARD_VERIFIED_DOC_WEALTH: Validated source of inheritance or private investment proceeds"
                ],
                mutation_rationale="Eliminates redundant audits for established, fully-papered high-net-worth customers."
            )
