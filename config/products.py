"""Banking products and onboarding channel risk configuration."""

from typing import Dict, Tuple

# Banking products available to individual customers
PRODUCT_RISK: Dict[str, Tuple[float, str]] = {
    "CURRENT_ACCOUNT": (15.0, "Standard retail checking account with debit card"),
    "SAVINGS_ACCOUNT": (10.0, "Interest-bearing savings account (low velocity)"),
    "MULTI_CURRENCY_WALLET": (45.0, "Multi-currency foreign exchange account (FX cross-border risk)"),
    "INTERNATIONAL_WIRE_SERVICE": (55.0, "SWIFT/Cross-border outbound and inbound wire transfer access"),
    "CRYPTO_GATEWAY_ACCESS": (75.0, "Direct integration with crypto on/off-ramps"),
    "CASH_DEPOSIT_SERVICE": (50.0, "High-volume cash deposit and branch teller facility"),
    "PRIVATE_BANKING_WEALTH": (60.0, "High-net-worth private wealth management and investment vehicle"),
    "MARGIN_TRADING_ACCOUNT": (40.0, "Securities, derivatives, and margin trading account"),
    "PREPAID_TRAVEL_CARD": (35.0, "Prepaid reloadable payment card"),
}

# Onboarding channels
CHANNEL_RISK: Dict[str, Tuple[float, str]] = {
    "BRANCH_IN_PERSON": (10.0, "In-branch face-to-face with biometric chip passport validation"),
    "DIGITAL_EKYC_BIOMETRIC": (25.0, "Remote digital onboarding with active liveness check and e-ID"),
    "DIGITAL_WEB_BASIC": (45.0, "Web portal submission without active liveness video verification"),
    "THIRD_PARTY_INTRODUCER": (60.0, "Introduced through third-party broker or wealth manager"),
}

# Declared relationship purpose and nature risk
PURPOSE_RISK: Dict[str, Tuple[float, str]] = {
    "SALARY_AND_LIVING_EXPENSES": (10.0, "Standard receipt of employment salary and household living costs"),
    "PERSONAL_SAVINGS": (15.0, "Accumulation of personal and family savings"),
    "RETIREMENT_PENSION": (10.0, "Management of pension disbursements and post-retirement funds"),
    "CROSS_BORDER_REMITTANCES": (50.0, "Regular cross-border transfers to family/overseas dependents"),
    "INVESTMENT_WEALTH_GROWTH": (35.0, "Securities, ETFs, mutual funds, and property investments"),
    "CRYPTO_ASSET_TRADING": (75.0, "High-frequency virtual asset trading and arbitrage"),
    "E_COMMERCE_FREELANCE_CONSULTING": (40.0, "Independent consulting and online digital client billings"),
    "REAL_ESTATE_HOLDINGS": (50.0, "Rental income and property acquisition management"),
    "GAMBLING_PROCEEDS": (85.0, "High-risk gambling and speculative sports wagering proceeds"),
}
