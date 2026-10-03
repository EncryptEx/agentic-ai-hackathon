"""Transaction models for transaction monitoring."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class TransactionType(str, Enum):
    SALARY_CREDIT = "SALARY_CREDIT"
    ACH_DEPOSIT = "ACH_DEPOSIT"
    ACH_WITHDRAWAL = "ACH_WITHDRAWAL"
    DOMESTIC_WIRE_IN = "DOMESTIC_WIRE_IN"
    DOMESTIC_WIRE_OUT = "DOMESTIC_WIRE_OUT"
    INTERNATIONAL_WIRE_IN = "INTERNATIONAL_WIRE_IN"
    INTERNATIONAL_WIRE_OUT = "INTERNATIONAL_WIRE_OUT"
    CASH_DEPOSIT = "CASH_DEPOSIT"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"
    POS_PURCHASE = "POS_PURCHASE"
    ONLINE_PURCHASE = "ONLINE_PURCHASE"
    CRYPTO_PURCHASE = "CRYPTO_PURCHASE"
    CRYPTO_CASHOUT = "CRYPTO_CASHOUT"
    P2P_TRANSFER_IN = "P2P_TRANSFER_IN"
    P2P_TRANSFER_OUT = "P2P_TRANSFER_OUT"
    ATM_WITHDRAWAL = "ATM_WITHDRAWAL"

class TransactionDirection(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"

class Transaction(BaseModel):
    transaction_id: str = Field(..., description="Unique transaction ID (e.g., TXN-981248)")
    customer_id: str
    timestamp: str = Field(..., description="ISO 8601 timestamp (YYYY-MM-DDTHH:MM:SS)")
    transaction_type: TransactionType
    direction: TransactionDirection
    amount_usd: float
    currency: str = "USD"
    
    # Counterparty details
    counterparty_name: str
    counterparty_country: str = Field(..., description="ISO-2 country code of counterparty")
    counterparty_account: Optional[str] = None
    counterparty_category: str = Field(
        ..., 
        description="e.g. EMPLOYER, UTILITY, RETAILER, CRYPTO_EXCHANGE, OFFSHORE_CORP, INDIVIDUAL, ATM, PEER"
    )
    channel: str = Field(..., description="e.g. SWIFT, ACH, ATM, MOBILE_APP, WEB_PORTAL, BRANCH_TELLER")
    reference_narrative: str
    
    # Digital Identity & Fraud Metadata
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    ip_country: Optional[str] = None
    is_card_present: Optional[bool] = None
    card_entry_mode: Optional[str] = None # e.g. CHIP_EMV, CONTACTLESS, CNP_ECOMMERCE, MAGSTRIPE
    auth_status: str = "AUTHORIZED" # AUTHORIZED, DECLINED_SUSPECTED_FRAUD, DECLINED_INSUFFICIENT_FUNDS
    is_new_payee: bool = False
    payee_first_seen_hours: Optional[float] = None

    # Synthetic ground-truth indicators (useful for validation and testing)
    is_suspicious_synthetic: bool = False
    synthetic_typology_tag: Optional[str] = None
    is_fraud_synthetic: bool = False
    fraud_typology_tag: Optional[str] = None
