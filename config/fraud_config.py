"""Fraud detection rule parameters, scoring thresholds, and typologies."""

from typing import Dict, Any

# Integrated FRAML (Fraud + Anti-Money Laundering) Pillar Weights (Sum = 1.0)
FRAML_PILLAR_WEIGHTS: Dict[str, float] = {
    "CUSTOMER_KYC": 0.20,       # Demographic, Citizenship, Residency, PEP, Adverse Media
    "PURPOSE_NATURE": 0.10,     # Declared purpose, source of wealth plausibility
    "PRODUCTS_CHANNELS": 0.10,  # Product mix, onboarding channel risk
    "AML_BEHAVIOR": 0.30,       # Transaction monitoring AML alerts (Structuring, Mules, Corridors)
    "FRAUD_RISK": 0.30          # First-party & Third-party Fraud (ATO, Card Testing, APP Scams, Bust-out)
}

FRAUD_RULES_CONFIG: Dict[str, Any] = {
    # FR-01: Account Takeover (ATO) & Impossible Travel
    "ATO_MIN_DRAIN_AMOUNT_USD": 2500.0,
    "ATO_IMPOSSIBLE_TRAVEL_SPEED_KMH": 900.0, # Faster than commercial jet
    "ATO_TIME_WINDOW_MINUTES": 180,
    "ATO_RISK_SCORE": 92.0,

    # FR-02: Card Testing / Micro-probing followed by High-Dollar Drain
    "CARD_TEST_MICRO_MAX_USD": 3.00,
    "CARD_TEST_MIN_PROBES": 2,
    "CARD_TEST_DRAIN_MIN_USD": 1500.0,
    "CARD_TEST_WINDOW_MINUTES": 60,
    "CARD_TEST_RISK_SCORE": 88.0,

    # FR-03: Authorized Push Payment (APP) / Investment & Romance Scam
    "APP_SCAM_MIN_OUTFLOW_USD": 4000.0,
    "APP_SCAM_RAPID_TX_COUNT": 2,
    "APP_SCAM_NEW_PAYEE_HOURS": 24.0,
    "APP_SCAM_RISK_SCORE": 85.0,

    # FR-04: First-Party Bust-Out / Deposit Kiting Fraud
    "BUSTOUT_MIN_DEPOSIT_USD": 8000.0,
    "BUSTOUT_WITHDRAWAL_RATIO": 0.80,
    "BUSTOUT_TIME_WINDOW_HOURS": 48,
    "BUSTOUT_RISK_SCORE": 90.0,

    # FR-05: Synthetic Identity Fraud & Burner Contact
    "SYNTHETIC_ID_DISPOSABLE_EMAIL_PENALTY": 35.0,
    "SYNTHETIC_ID_VOIP_PHONE_PENALTY": 30.0,
    "SYNTHETIC_ID_ADDRESS_MISMATCH_PENALTY": 25.0,
    "SYNTHETIC_ID_SCORE_THRESHOLD": 60.0,

    # FR-06: SIM Swap / Credential Reset & Outbound Wire Drain
    "SIM_SWAP_DRAIN_MIN_USD": 3000.0,
    "SIM_SWAP_MAX_HOURS_POST_RESET": 24.0,
    "SIM_SWAP_RISK_SCORE": 91.0,

    # FR-07: Friendly Fraud / Chargeback Abuse & First-Party Merchant Claims
    "FRIENDLY_FRAUD_MIN_DISPUTES": 2,
    "FRIENDLY_FRAUD_MIN_AMOUNT_USD": 1200.0,
    "FRIENDLY_FRAUD_RISK_SCORE": 78.0,

    # FR-08: BIN Attack & High-Velocity Automated Card Testing
    "BIN_ATTACK_MIN_DECLINES": 3,
    "BIN_ATTACK_WINDOW_MINUTES": 30,
    "BIN_ATTACK_RISK_SCORE": 89.0,

    # FR-09: Business Email Compromise (BEC) / Executive Impersonation
    "BEC_MIN_AMOUNT_USD": 10000.0,
    "BEC_RISK_SCORE": 93.0,

    # FR-10: Adversary-in-the-Middle (AitM) Phishing Session Hijack
    "AITM_SESSION_WINDOW_MINUTES": 60,
    "AITM_MIN_DRAIN_USD": 2000.0,
    "AITM_RISK_SCORE": 94.0,

    # FR-11: Counterfeit Overpayment / Fake Refund Scam
    "OVERPAYMENT_MIN_DEPOSIT_USD": 5000.0,
    "OVERPAYMENT_REFUND_RATIO": 0.60,
    "OVERPAYMENT_WINDOW_HOURS": 72,
    "OVERPAYMENT_RISK_SCORE": 86.0,
}
