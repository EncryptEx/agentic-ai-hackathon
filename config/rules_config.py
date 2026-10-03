"""Scoring weights, thresholds, and AML rule parameters."""

from typing import Dict, Any

# Multi-Pillar Risk Engine Weights (Sum = 1.0)
RISK_PILLAR_WEIGHTS: Dict[str, float] = {
    "CUSTOMER_KYC": 0.30,       # Demographic, Citizenship, Residency, PEP, Adverse Media, Occupation
    "PURPOSE_NATURE": 0.15,     # Declared purpose of account, source of wealth plausibility
    "PRODUCTS_CHANNELS": 0.15,  # Product mix, onboarding channel risk
    "TRANSACTION_BEHAVIOR": 0.40 # Transaction monitoring alerts, volume/frequency anomalies, typologies
}

# Overall Risk Score Cutoffs (0 to 100)
RISK_TIER_CUTOFFS = {
    "LOW": (0.0, 34.99),
    "MEDIUM": (35.0, 59.99),
    "HIGH": (60.0, 84.99),
    "CRITICAL": (85.0, 100.0) # High-priority EDD, Potential SAR / Account Restriction
}

# Transaction Monitoring Rule Parameters
TM_RULES_CONFIG: Dict[str, Any] = {
    # Structuring / Smurfing: Evading Currency Transaction Reporting (CTR) threshold
    "CTR_THRESHOLD_USD": 10000.0,
    "STRUCTURING_LOWER_BOUND_USD": 7500.0,
    "STRUCTURING_UPPER_BOUND_USD": 9999.0,
    "STRUCTURING_WINDOW_DAYS": 14,
    "STRUCTURING_MIN_COUNT": 3,
    "STRUCTURING_RISK_SCORE": 85.0,

    # Rapid Movement of Funds / Pass-through Mule Account
    # Account receives funds and immediately dissipates >85% within 48h
    "MULE_MIN_INFLOW_USD": 5000.0,
    "MULE_OUTFLOW_RATIO_TRIGGER": 0.85,
    "MULE_TIME_WINDOW_HOURS": 48,
    "MULE_RISK_SCORE": 80.0,

    # Profile Turnover Deviation (Actual vs Declared Expected Monthly Turnover)
    "TURNOVER_DEVIATION_MODERATE_RATIO": 2.5,  # Actual >= 2.5x declared
    "TURNOVER_DEVIATION_HIGH_RATIO": 5.0,      # Actual >= 5.0x declared
    "TURNOVER_DEVIATION_EXTREME_RATIO": 10.0,  # Actual >= 10.0x declared

    # Single Transaction Outlier (vs Declared Maximum Single Transaction)
    "SINGLE_TX_DEVIATION_RATIO": 4.0,          # Single tx >= 4x declared max single tx

    # Dormancy Break / Sudden Surge
    "DORMANCY_MIN_DAYS_INACTIVE": 60,
    "DORMANCY_BURST_MIN_AMOUNT_USD": 10000.0,

    # Round Amount Transactions
    "ROUND_AMOUNT_MIN_COUNT": 4,
    "ROUND_AMOUNT_WINDOW_DAYS": 14,
    "ROUND_AMOUNT_DENOMINATIONS": [1000, 2000, 5000, 10000],

    # High-Risk Country Corridors
    "CORRIDOR_SANCTION_RISK_SCORE": 95.0,
    "CORRIDOR_GREYLIST_RISK_SCORE": 70.0,
    "CORRIDOR_OFFSHORE_RISK_SCORE": 60.0,

    # Crypto Velocity / High-Frequency Crypto Ramps
    "CRYPTO_BURST_MIN_AMOUNT_USD": 15000.0,
    "CRYPTO_BURST_MIN_TX_COUNT": 3,
}
