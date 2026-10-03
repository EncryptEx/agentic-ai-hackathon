"""Synthetic individual customer generator for KYC compliance."""

import random
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from faker import Faker

from models.customer import CustomerProfile, PEPStatus, AdverseMedia, SanctionStatus
from config.jurisdictions import (
    FATF_BLACKLIST, FATF_GREYLIST, SECRECY_OFFSHORE, 
    MEDIUM_RISK_COUNTRIES, LOW_RISK_COUNTRIES
)
from config.occupations import (
    HIGH_RISK_OCCUPATIONS, MEDIUM_RISK_OCCUPATIONS, LOW_RISK_OCCUPATIONS
)

fake = Faker()

ARCHETYPE_CONFIGS = {
    "DOMESTIC_SALARIED_LOW_RISK": {
        "weight": 0.45,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["SOFTWARE_ENGINEER", "PHYSICIAN_DOCTOR", "NURSE", "TEACHER_PROFESSOR", "ACCOUNTANT_CERTIFIED", "CORPORATE_EXECUTIVE"],
        "citizenships": ["US", "GB", "DE", "FR", "CA", "AU", "JP", "NL"],
        "residence_match": True,
        "income_range": (45000, 180000),
        "turnover_mult": (0.6, 1.2), # relative to monthly salary
        "purposes": ["SALARY_AND_LIVING_EXPENSES", "PERSONAL_SAVINGS"],
        "products": ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT"],
        "channels": ["BRANCH_IN_PERSON", "DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Employment Salary & Bonuses",
        "source_wealth": "Accumulated Career Earnings",
    },
    "RETIRED_PENSIONER": {
        "weight": 0.12,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["RETIRED_PENSIONER"],
        "citizenships": ["US", "GB", "DE", "FR", "CA", "AU", "ES", "IT"],
        "residence_match": True,
        "income_range": (28000, 75000),
        "turnover_mult": (0.5, 0.9),
        "purposes": ["RETIREMENT_PENSION", "PERSONAL_SAVINGS"],
        "products": ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT"],
        "channels": ["BRANCH_IN_PERSON"],
        "source_funds": "State & Private Pension Disbursements",
        "source_wealth": "Lifetime Savings & Realized Real Estate",
    },
    "TECH_EXPAT_DIGITAL_NOMAD": {
        "weight": 0.10,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["SOFTWARE_ENGINEER", "CORPORATE_EXECUTIVE"],
        "citizenships": ["DE", "FR", "GB", "IN", "BR", "CA", "US"],
        "residence_match": False, # Expat living abroad
        "income_range": (85000, 240000),
        "turnover_mult": (0.8, 1.5),
        "purposes": ["SALARY_AND_LIVING_EXPENSES", "CROSS_BORDER_REMITTANCES", "INVESTMENT_WEALTH_GROWTH"],
        "products": ["CURRENT_ACCOUNT", "MULTI_CURRENCY_WALLET", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "International Tech Consulting & Salary",
        "source_wealth": "Consulting Revenue & Liquid Stock Equity",
    },
    "HIGH_NET_WORTH_INVESTOR": {
        "weight": 0.08,
        "pep_prob": 0.05,
        "adverse_media_prob": 0.02,
        "sanction_prob": 0.0,
        "occupations": ["CORPORATE_EXECUTIVE", "REAL_ESTATE_DEVELOPER_SPEC"],
        "citizenships": ["US", "GB", "CH", "SG", "AE", "DE"],
        "residence_match": True,
        "income_range": (350000, 1500000),
        "turnover_mult": (1.0, 3.0),
        "purposes": ["INVESTMENT_WEALTH_GROWTH", "REAL_ESTATE_HOLDINGS"],
        "products": ["CURRENT_ACCOUNT", "PRIVATE_BANKING_WEALTH", "MARGIN_TRADING_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["BRANCH_IN_PERSON", "THIRD_PARTY_INTRODUCER"],
        "source_funds": "Dividends, Capital Gains, and Real Estate Rentals",
        "source_wealth": "Family Trust Distribution & Multi-Asset Portfolio",
    },
    "DOMESTIC_PEP_OFFICIAL": {
        "weight": 0.04,
        "pep_prob": 1.0,
        "pep_type": PEPStatus.DOMESTIC_PEP,
        "adverse_media_prob": 0.15,
        "sanction_prob": 0.0,
        "occupations": ["POLITICIAN_SENIOR"],
        "citizenships": ["US", "GB", "FR", "DE"],
        "residence_match": True,
        "income_range": (140000, 260000),
        "turnover_mult": (0.8, 1.4),
        "purposes": ["SALARY_AND_LIVING_EXPENSES", "PERSONAL_SAVINGS"],
        "products": ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["BRANCH_IN_PERSON"],
        "source_funds": "Government Official Ministerial Remuneration",
        "source_wealth": "Inherited Family Estate & Public Compensation",
    },
    "FOREIGN_PEP_ASSOCIATE": {
        "weight": 0.03,
        "pep_prob": 1.0,
        "pep_type": PEPStatus.PEP_ASSOCIATE,
        "adverse_media_prob": 0.35,
        "sanction_prob": 0.0,
        "occupations": ["IMPORT_EXPORT_TRADER", "REAL_ESTATE_DEVELOPER_SPEC"],
        "citizenships": ["NG", "ZA", "TR", "BR", "MX", "ID"],
        "residence_match": False,
        "income_range": (180000, 500000),
        "turnover_mult": (1.5, 3.5),
        "purposes": ["INVESTMENT_WEALTH_GROWTH", "CROSS_BORDER_REMITTANCES"],
        "products": ["CURRENT_ACCOUNT", "MULTI_CURRENCY_WALLET", "INTERNATIONAL_WIRE_SERVICE", "PRIVATE_BANKING_WEALTH"],
        "channels": ["THIRD_PARTY_INTRODUCER", "DIGITAL_WEB_BASIC"],
        "source_funds": "Family Holding Company Retained Earnings",
        "source_wealth": "Offshore Holdings & State Concessions",
    },
    "SOLE_PROPRIETOR_CASH_RETAIL": {
        "weight": 0.07,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.02,
        "sanction_prob": 0.0,
        "occupations": ["NIGHTCLUB_RESTAURANT_OWNER", "USED_CAR_DEALER", "RETAIL_EMPLOYEE"],
        "citizenships": ["US", "GB", "DE", "ES", "IT"],
        "residence_match": True,
        "income_range": (55000, 130000),
        "turnover_mult": (1.0, 2.0),
        "purposes": ["E_COMMERCE_FREELANCE_CONSULTING", "SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE"],
        "channels": ["BRANCH_IN_PERSON"],
        "source_funds": "Cash & Card Sales from Sole Proprietorship",
        "source_wealth": "Commercial Enterprise Reinvested Profits",
    },
    # Suspicious / High-Risk Typologies
    "STRUCTURING_CASH_OPERATOR": {
        "weight": 0.04,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.05,
        "sanction_prob": 0.0,
        "occupations": ["USED_CAR_DEALER", "PAWNBROKER", "SCRAP_METAL_MERCHANT"],
        "citizenships": ["US", "GB", "CA", "DE"],
        "residence_match": True,
        "income_range": (45000, 85000), # Declares modest income
        "turnover_mult": (0.8, 1.2),   # Declares low turnover, but will deposit heavily!
        "purposes": ["SALARY_AND_LIVING_EXPENSES", "PERSONAL_SAVINGS"],
        "products": ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_WEB_BASIC", "BRANCH_IN_PERSON"],
        "source_funds": "Vehicle Trading & Independent Salvage",
        "source_wealth": "Accumulated Cash Operations",
    },
    "STUDENT_MONEY_MULE": {
        "weight": 0.03,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["STUDENT"],
        "citizenships": ["US", "GB", "NG", "VN", "RO"],
        "residence_match": True,
        "income_range": (12000, 24000), # Very low declared student income
        "turnover_mult": (0.5, 1.0),   # Expects $1k/mo, but will receive thousands!
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT", "CRYPTO_GATEWAY_ACCESS", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_WEB_BASIC"],
        "source_funds": "Parental Allowance & Scholarship",
        "source_wealth": "Family Support",
    },
    "SANCTION_GREYLIST_CORRIDOR": {
        "weight": 0.02,
        "pep_prob": 0.10,
        "adverse_media_prob": 0.20,
        "sanction_prob": 0.05, # Some have potential screening hits
        "occupations": ["IMPORT_EXPORT_TRADER", "OFFSHORE_TRUSTEE"],
        "citizenships": ["SY", "IR", "MM", "YE", "HT", "KY", "VG", "PA"],
        "residence_match": False,
        "income_range": (90000, 280000),
        "turnover_mult": (1.5, 3.0),
        "purposes": ["CROSS_BORDER_REMITTANCES", "E_COMMERCE_FREELANCE_CONSULTING"],
        "products": ["CURRENT_ACCOUNT", "MULTI_CURRENCY_WALLET", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_WEB_BASIC", "THIRD_PARTY_INTRODUCER"],
        "source_funds": "Cross-border Logistics & Consulting Fees",
        "source_wealth": "Offshore Trade Invoicing",
    },
    "ADVERSE_MEDIA_FINANCIAL_CRIME": {
        "weight": 0.02,
        "pep_prob": 0.05,
        "adverse_media_prob": 1.0,
        "adverse_media_type": AdverseMedia.FINANCIAL_CRIME,
        "sanction_prob": 0.0,
        "occupations": ["CRYPTO_BROKER", "CASINO_OPERATOR", "MSB_AGENT"],
        "citizenships": ["US", "GB", "CA", "AU", "DE"],
        "residence_match": True,
        "income_range": (150000, 450000),
        "turnover_mult": (1.0, 2.5),
        "purposes": ["CRYPTO_ASSET_TRADING", "INVESTMENT_WEALTH_GROWTH"],
        "products": ["CURRENT_ACCOUNT", "CRYPTO_GATEWAY_ACCESS", "MARGIN_TRADING_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Crypto Mining & High-Frequency Virtual Arbitrage",
        "source_wealth": "Early Crypto Investments & Private Liquidity Pools",
    },
    # Fraud Typology Archetypes (First-Party & Third-Party Fraud)
    "ACCOUNT_TAKEOVER_VICTIM": {
        "weight": 0.04,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["TEACHER_PROFESSOR", "ACCOUNTANT_CERTIFIED", "CORPORATE_EXECUTIVE"],
        "citizenships": ["US", "GB", "DE", "FR", "CA"],
        "residence_match": True,
        "income_range": (65000, 140000),
        "turnover_mult": (0.8, 1.2),
        "purposes": ["SALARY_AND_LIVING_EXPENSES", "PERSONAL_SAVINGS"],
        "products": ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Employment Salary",
        "source_wealth": "Personal Savings",
    },
    "CARD_FRAUD_VICTIM": {
        "weight": 0.05,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["SOFTWARE_ENGINEER", "PHYSICIAN_DOCTOR", "RETAIL_EMPLOYEE"],
        "citizenships": ["US", "GB", "DE", "CA"],
        "residence_match": True,
        "income_range": (50000, 120000),
        "turnover_mult": (0.7, 1.1),
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Employment Salary",
        "source_wealth": "Personal Earnings",
    },
    "APP_SCAM_VICTIM": {
        "weight": 0.04,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["RETIRED_PENSIONER", "TEACHER_PROFESSOR"],
        "citizenships": ["US", "GB", "DE", "AU"],
        "residence_match": True,
        "income_range": (35000, 95000),
        "turnover_mult": (0.6, 1.0),
        "purposes": ["PERSONAL_SAVINGS", "RETIREMENT_PENSION"],
        "products": ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["BRANCH_IN_PERSON"],
        "source_funds": "Retirement Pension & Lifetime Savings",
        "source_wealth": "Realized Home Equity",
    },
    "FIRST_PARTY_BUST_OUT": {
        "weight": 0.03,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["STUDENT", "RETAIL_EMPLOYEE", "USED_CAR_DEALER"],
        "citizenships": ["US", "GB", "CA"],
        "residence_match": True,
        "income_range": (24000, 45000),
        "turnover_mult": (0.8, 1.2),
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE"],
        "channels": ["DIGITAL_WEB_BASIC"],
        "source_funds": "Short-term Contract Wages",
        "source_wealth": "Personal Checking",
    },
    "SYNTHETIC_IDENTITY_FRAUD": {
        "weight": 0.03,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["INDEPENDENT_LEGAL_CONSULTANT", "IMPORT_EXPORT_TRADER"],
        "citizenships": ["US", "GB"],
        "residence_match": True,
        "income_range": (85000, 160000), # Fabricated high income to obtain credit
        "turnover_mult": (1.0, 2.0),
        "purposes": ["INVESTMENT_WEALTH_GROWTH"],
        "products": ["CURRENT_ACCOUNT", "MARGIN_TRADING_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_WEB_BASIC"],
        "source_funds": "Consulting Revenue (Fabricated)",
        "source_wealth": "Private Investment (Unverified)",
    },
    # New Fraud Archetypes
    "SIM_SWAP_VICTIM": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["CORPORATE_EXECUTIVE", "PHYSICIAN_DOCTOR"],
        "citizenships": ["US", "GB", "CA", "DE"],
        "residence_match": True,
        "income_range": (95000, 220000),
        "turnover_mult": (0.7, 1.2),
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Executive Remuneration",
        "source_wealth": "Personal Savings & Investments",
    },
    "FRIENDLY_FRAUD_ABUSER": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["STUDENT", "RETAIL_EMPLOYEE", "SOFTWARE_ENGINEER"],
        "citizenships": ["US", "GB", "DE"],
        "residence_match": True,
        "income_range": (35000, 75000),
        "turnover_mult": (1.0, 1.8),
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Salary & Contract Work",
        "source_wealth": "Current Earnings",
    },
    "BIN_ATTACK_TARGET": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["TEACHER_PROFESSOR", "ACCOUNTANT_CERTIFIED"],
        "citizenships": ["US", "GB", "FR"],
        "residence_match": True,
        "income_range": (48000, 85000),
        "turnover_mult": (0.6, 1.0),
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT"],
        "channels": ["BRANCH_IN_PERSON"],
        "source_funds": "Salary",
        "source_wealth": "Savings",
    },
    "BEC_EXECUTIVE_TARGET": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["CORPORATE_EXECUTIVE", "ACCOUNTANT_CERTIFIED"],
        "citizenships": ["US", "GB", "SG", "DE"],
        "residence_match": True,
        "income_range": (180000, 420000),
        "turnover_mult": (1.0, 2.5),
        "purposes": ["SALARY_AND_LIVING_EXPENSES", "INVESTMENT_WEALTH_GROWTH"],
        "products": ["CURRENT_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Corporate Executive Salary",
        "source_wealth": "Equity Grants & Accumulated Assets",
    },
    "AITM_PHISHING_VICTIM": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["SOFTWARE_ENGINEER", "CORPORATE_EXECUTIVE"],
        "citizenships": ["US", "GB", "CA"],
        "residence_match": True,
        "income_range": (85000, 165000),
        "turnover_mult": (0.8, 1.3),
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Employment Compensation",
        "source_wealth": "Personal Checking",
    },
    "OVERPAYMENT_SCAM_VICTIM": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["RETIRED_PENSIONER", "RETAIL_EMPLOYEE"],
        "citizenships": ["US", "GB", "CA", "AU"],
        "residence_match": True,
        "income_range": (30000, 65000),
        "turnover_mult": (0.5, 0.9),
        "purposes": ["SALARY_AND_LIVING_EXPENSES", "PERSONAL_SAVINGS"],
        "products": ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT"],
        "channels": ["BRANCH_IN_PERSON"],
        "source_funds": "Pension / Part-time Wages",
        "source_wealth": "Personal Savings",
    },
    # New AML Archetypes
    "TBML_FRONT_OPERATOR": {
        "weight": 0.02,
        "pep_prob": 0.05,
        "adverse_media_prob": 0.10,
        "sanction_prob": 0.0,
        "occupations": ["IMPORT_EXPORT_TRADER"],
        "citizenships": ["AE", "HK", "SG", "US", "GB"],
        "residence_match": False,
        "income_range": (140000, 380000),
        "turnover_mult": (2.0, 5.0),
        "purposes": ["E_COMMERCE_FREELANCE_CONSULTING", "CROSS_BORDER_REMITTANCES"],
        "products": ["CURRENT_ACCOUNT", "MULTI_CURRENCY_WALLET", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["THIRD_PARTY_INTRODUCER", "DIGITAL_WEB_BASIC"],
        "source_funds": "Import / Export Consignment Turnover",
        "source_wealth": "Commercial Trade Equity",
    },
    "FAN_OUT_LAYERING_NETWORK": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.05,
        "sanction_prob": 0.0,
        "occupations": ["USED_CAR_DEALER", "RETAIL_EMPLOYEE"],
        "citizenships": ["US", "GB", "CA"],
        "residence_match": True,
        "income_range": (40000, 80000),
        "turnover_mult": (1.5, 3.5),
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT", "CRYPTO_GATEWAY_ACCESS", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_WEB_BASIC"],
        "source_funds": "Brokerage Commissions",
        "source_wealth": "Liquid Cash Holdings",
    },
    "CUCKOO_SMURFING_RECIPIENT": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["STUDENT", "IMPORT_EXPORT_TRADER"],
        "citizenships": ["GB", "US", "CA", "AU"],
        "residence_match": True,
        "income_range": (28000, 70000),
        "turnover_mult": (1.0, 2.5),
        "purposes": ["CROSS_BORDER_REMITTANCES", "PERSONAL_SAVINGS"],
        "products": ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE"],
        "channels": ["BRANCH_IN_PERSON"],
        "source_funds": "Family Overseas Support",
        "source_wealth": "Hawala Remittance Matching",
    },
    "CRYPTO_MIXER_OPERATOR": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.15,
        "sanction_prob": 0.0,
        "occupations": ["CRYPTO_BROKER"],
        "citizenships": ["US", "GB", "DE", "NL"],
        "residence_match": True,
        "income_range": (120000, 350000),
        "turnover_mult": (2.0, 6.0),
        "purposes": ["CRYPTO_ASSET_TRADING"],
        "products": ["CURRENT_ACCOUNT", "CRYPTO_GATEWAY_ACCESS", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["DIGITAL_EKYC_BIOMETRIC"],
        "source_funds": "Virtual Asset Trading & Liquidity Provision",
        "source_wealth": "Decentralized Finance Yield",
    },
    "HUMAN_TRAFFICKING_RING": {
        "weight": 0.01,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.10,
        "sanction_prob": 0.0,
        "occupations": ["NIGHTCLUB_RESTAURANT_OWNER", "RETAIL_EMPLOYEE"],
        "citizenships": ["US", "GB", "ES", "IT"],
        "residence_match": True,
        "income_range": (35000, 65000),
        "turnover_mult": (1.5, 3.0),
        "purposes": ["SALARY_AND_LIVING_EXPENSES"],
        "products": ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE"],
        "channels": ["DIGITAL_WEB_BASIC"],
        "source_funds": "Hospitality Wages",
        "source_wealth": "Cash Extractions",
    },
    "LOAN_WASH_BORROWER": {
        "weight": 0.02,
        "pep_prob": 0.0,
        "adverse_media_prob": 0.0,
        "sanction_prob": 0.0,
        "occupations": ["REAL_ESTATE_DEVELOPER_SPEC", "USED_CAR_DEALER"],
        "citizenships": ["US", "GB", "CA"],
        "residence_match": True,
        "income_range": (90000, 210000),
        "turnover_mult": (1.2, 2.5),
        "purposes": ["INVESTMENT_WEALTH_GROWTH"],
        "products": ["CURRENT_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"],
        "channels": ["BRANCH_IN_PERSON"],
        "source_funds": "Real Estate Rental Yield",
        "source_wealth": "Property Holdings",
    }
}

class CustomerGenerator:
    """Generates synthetic individual customer profiles with realistic KYC attributes."""

    def __init__(self, seed: Optional[int] = 42):
        if seed is not None:
            random.seed(seed)
            Faker.seed(seed)
        self.faker = Faker()

    def generate_customer(self, customer_id: str, archetype_name: Optional[str] = None) -> CustomerProfile:
        if archetype_name is None:
            # Weighted random selection
            archetypes = list(ARCHETYPE_CONFIGS.keys())
            weights = [cfg["weight"] for cfg in ARCHETYPE_CONFIGS.values()]
            archetype_name = random.choices(archetypes, weights=weights, k=1)[0]

        cfg = ARCHETYPE_CONFIGS[archetype_name]
        
        # Gender & Name
        first_name = self.faker.first_name()
        last_name = self.faker.last_name()
        
        # Age & DOB
        if archetype_name == "RETIRED_PENSIONER":
            age = random.randint(66, 85)
        elif archetype_name == "STUDENT_MONEY_MULE":
            age = random.randint(18, 24)
        else:
            age = random.randint(25, 64)
            
        birth_date = datetime.now() - timedelta(days=age * 365 + random.randint(1, 360))
        dob_str = birth_date.strftime("%Y-%m-%d")
        
        # Citizenship & Residence
        citizenship = random.choice(cfg["citizenships"])
        if cfg["residence_match"]:
            residence_country = citizenship
        else:
            # Foreign resident, living in a primary hub (e.g. US, GB, DE, SG, AE)
            safe_hosts = ["US", "GB", "DE", "SG", "AE", "FR", "CA"]
            residence_country = random.choice([c for c in safe_hosts if c != citizenship])

        dual_citizenship = None
        if random.random() < 0.12 and citizenship in LOW_RISK_COUNTRIES:
            dual_citizenship = random.choice(["CA", "IE", "IT", "FR", "AU"])
            
        tax_residence = residence_country if random.random() < 0.90 else citizenship

        # Address
        address_city = self.faker.city()
        address_postal_code = self.faker.postcode()
        address_line = self.faker.street_address()

        # Occupation
        occ_key = random.choice(cfg["occupations"])
        occ_name = occ_key.replace("_", " ").title()
        
        # Employer
        employer = None
        if occ_key not in ["RETIRED_PENSIONER", "STUDENT"]:
            employer = f"{self.faker.company()} Ltd"

        # Financials
        annual_income = round(random.uniform(*cfg["income_range"]), -2)
        net_worth_multiplier = random.uniform(1.5, 4.0)
        if archetype_name == "HIGH_NET_WORTH_INVESTOR":
            net_worth_multiplier = random.uniform(5.0, 15.0)
        net_worth = round(annual_income * net_worth_multiplier, -2)

        monthly_salary = annual_income / 12.0
        turnover_ratio = random.uniform(*cfg["turnover_mult"])
        expected_monthly_turnover = round(monthly_salary * turnover_ratio, -2)
        expected_max_single_tx = round(expected_monthly_turnover * random.uniform(0.3, 0.7), -2)

        # Purpose, Products, Channels
        purpose = random.choice(cfg["purposes"])
        channel = random.choice(cfg["channels"])
        products = list(cfg["products"])
        # Some customers have additional basic products
        if "CURRENT_ACCOUNT" not in products:
            products.append("CURRENT_ACCOUNT")

        # Onboarding date (within last 3 years)
        days_ago = random.randint(30, 1095)
        onboarding_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        # PEP Status
        pep_status = PEPStatus.NONE
        pep_details = None
        if "pep_type" in cfg:
            pep_status = cfg["pep_type"]
            pep_details = f"Identified as {pep_status.value} - Senior public role oversight."
        elif random.random() < cfg.get("pep_prob", 0.0):
            pep_status = random.choice([PEPStatus.DOMESTIC_PEP, PEPStatus.PEP_ASSOCIATE])
            pep_details = f"Designated PEP match under national advisory registry."

        # Adverse Media
        adverse_media = AdverseMedia.NONE
        adverse_media_details = None
        if "adverse_media_type" in cfg:
            adverse_media = cfg["adverse_media_type"]
            adverse_media_details = f"Designated screening hit: identified in international regulatory financial crime dossier."
        elif random.random() < cfg.get("adverse_media_prob", 0.0):
            adverse_media = random.choice([
                AdverseMedia.FINANCIAL_CRIME,
                AdverseMedia.FRAUD,
                AdverseMedia.CORRUPTION_BRIBERY,
                AdverseMedia.REGULATORY_ENFORCEMENT
            ])
            adverse_media_details = f"Screening match on public records: regulatory scrutiny concerning {adverse_media.value.lower()}."

        # Sanctions Screening
        sanction_status = SanctionStatus.CLEAN
        sanction_details = None
        if random.random() < cfg.get("sanction_prob", 0.0):
            if citizenship in FATF_BLACKLIST or residence_country in FATF_BLACKLIST:
                sanction_status = SanctionStatus.CONFIRMED_HIT
                sanction_details = "Direct national jurisdiction comprehensive sanctions match."
            else:
                sanction_status = SanctionStatus.FALSE_POSITIVE_RESOLVED
                sanction_details = "Near name match with designated entity - secondary review cleared."

        # Digital Identity & Fraud Screening
        if archetype_name == "SYNTHETIC_IDENTITY_FRAUD":
            email_domain_type = "DISPOSABLE_TEMP"
            email_address = f"{first_name.lower()}{random.randint(10,99)}@throwawayinbox.com"
            phone_line_type = "VOIP_VIRTUAL"
            phone_number = f"+1-555-{random.randint(200,899)}-{random.randint(1000,9999)}"
            device_primary_id = f"DEV-BURNER-{random.randint(1000,9999)}"
            primary_ip_address = f"{random.randint(100, 190)}.{random.randint(10, 200)}.{random.randint(1, 250)}.{random.randint(1, 250)}"
            primary_ip_country = residence_country
            synthetic_identity_score = round(random.uniform(78.0, 94.0), 1)
            synthetic_id_indicators = [
                "Disposable temporary burner email domain (throwawayinbox.com)",
                "Virtual VoIP PBX phone number with no carrier subscriber record",
                "Synthetic Identity algorithm: SSN issue date conflicts with applicant birth year",
                "High velocity credit profile creation detected across regional bureau consortium"
            ]
        else:
            email_domain_type = "CORPORATE" if employer else "PUBLIC_FREE"
            dom = f"{employer.split()[0].lower().replace(',', '')}.com" if employer else random.choice(["gmail.com", "outlook.com", "icloud.com"])
            email_address = f"{first_name.lower()}.{last_name.lower()}@{dom}"
            phone_line_type = "MOBILE"
            phone_number = f"+1-{random.randint(201, 899)}-{random.randint(200, 899)}-{random.randint(1000, 9999)}"
            device_primary_id = f"DEV-{random.randint(100000, 999999)}"
            primary_ip_address = f"{random.randint(24, 198)}.{random.randint(10, 240)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
            primary_ip_country = residence_country
            synthetic_identity_score = round(random.uniform(2.0, 18.0), 1)
            synthetic_id_indicators = []

        return CustomerProfile(
            customer_id=customer_id,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=dob_str,
            age=age,
            citizenship=citizenship,
            dual_citizenship=dual_citizenship,
            residence_country=residence_country,
            tax_residence_country=tax_residence,
            address_city=address_city,
            address_postal_code=address_postal_code,
            address_line=address_line,
            occupation=occ_name,
            occupation_risk_key=occ_key,
            industry=occ_name,
            employer_name=employer,
            source_of_funds=cfg["source_funds"],
            source_of_wealth=cfg["source_wealth"],
            annual_income_usd=annual_income,
            net_worth_usd=net_worth,
            declared_expected_monthly_turnover_usd=expected_monthly_turnover,
            declared_expected_max_single_tx_usd=expected_max_single_tx,
            declared_purpose_nature=purpose,
            onboarding_channel=channel,
            onboarding_date=onboarding_date,
            products_held=products,
            pep_status=pep_status,
            pep_details=pep_details,
            adverse_media=adverse_media,
            adverse_media_details=adverse_media_details,
            sanction_status=sanction_status,
            sanction_details=sanction_details,
            email_address=email_address,
            email_domain_type=email_domain_type,
            phone_number=phone_number,
            phone_line_type=phone_line_type,
            device_primary_id=device_primary_id,
            primary_ip_address=primary_ip_address,
            primary_ip_country=primary_ip_country,
            synthetic_identity_score=synthetic_identity_score,
            synthetic_id_indicators=synthetic_id_indicators,
            archetype=archetype_name
        )

    def generate_batch(self, count: int = 100, prefix: str = "CUST") -> List[CustomerProfile]:
        """Generates a batch of diverse individual customer profiles."""
        customers = []
        for i in range(1, count + 1):
            cust_id = f"{prefix}-{i:05d}"
            profile = self.generate_customer(cust_id)
            customers.append(profile)
        return customers
