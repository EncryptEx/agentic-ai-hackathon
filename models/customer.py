"""Individual customer KYC data models."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class PEPStatus(str, Enum):
    NONE = "NONE"
    DOMESTIC_PEP = "DOMESTIC_PEP"
    FOREIGN_PEP = "FOREIGN_PEP"
    PEP_ASSOCIATE = "PEP_ASSOCIATE" # Family member or close associate

class AdverseMedia(str, Enum):
    NONE = "NONE"
    FINANCIAL_CRIME = "FINANCIAL_CRIME"
    CORRUPTION_BRIBERY = "CORRUPTION_BRIBERY"
    FRAUD = "FRAUD"
    REGULATORY_ENFORCEMENT = "REGULATORY_ENFORCEMENT"

class SanctionStatus(str, Enum):
    CLEAN = "CLEAN"
    FALSE_POSITIVE_RESOLVED = "FALSE_POSITIVE_RESOLVED"
    CONFIRMED_HIT = "CONFIRMED_HIT"

class CustomerProfile(BaseModel):
    customer_id: str = Field(..., description="Unique customer identifier (e.g., CUST-00101)")
    first_name: str
    last_name: str
    date_of_birth: str = Field(..., description="YYYY-MM-DD")
    age: int
    citizenship: str = Field(..., description="ISO 3166-1 alpha-2 country code")
    dual_citizenship: Optional[str] = None
    residence_country: str = Field(..., description="Country of primary residence")
    tax_residence_country: str
    address_city: str
    address_postal_code: str
    address_line: str
    
    # Financial & Employment KYC
    occupation: str
    occupation_risk_key: str
    industry: str
    employer_name: Optional[str] = None
    source_of_funds: str
    source_of_wealth: str
    annual_income_usd: float
    net_worth_usd: float
    declared_expected_monthly_turnover_usd: float
    declared_expected_max_single_tx_usd: float
    
    # Relationship Nature & Products
    declared_purpose_nature: str
    onboarding_channel: str
    onboarding_date: str = Field(..., description="YYYY-MM-DD")
    products_held: List[str]
    
    # Screening & Watchlists
    pep_status: PEPStatus = PEPStatus.NONE
    pep_details: Optional[str] = None
    adverse_media: AdverseMedia = AdverseMedia.NONE
    adverse_media_details: Optional[str] = None
    sanction_status: SanctionStatus = SanctionStatus.CLEAN
    sanction_details: Optional[str] = None

    # Digital Identity & Fraud Screening Attributes
    email_address: Optional[str] = None
    email_domain_type: str = "PUBLIC_FREE" # CORPORATE, PUBLIC_FREE, DISPOSABLE_TEMP
    phone_number: Optional[str] = None
    phone_line_type: str = "MOBILE" # MOBILE, LANDLINE, VOIP_VIRTUAL
    device_primary_id: Optional[str] = None
    primary_ip_address: Optional[str] = None
    primary_ip_country: Optional[str] = None
    synthetic_identity_score: float = 0.0 # 0-100 indicating likelihood of synthetic identity
    synthetic_id_indicators: List[str] = Field(default_factory=list)

    # Archetype tag (for benchmark and evaluation)
    archetype: str = Field(..., description="Synthetic archetype used to generate this profile")
