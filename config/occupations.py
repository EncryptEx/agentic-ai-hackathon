"""Occupation and industry sector AML risk configuration."""

from typing import Dict, Tuple, List

# High Risk Occupations & Industry Sectors
HIGH_RISK_OCCUPATIONS: Dict[str, Tuple[float, str]] = {
    "CASINO_OPERATOR": (85.0, "Gambling and casino operations (high money laundering typology)"),
    "CRYPTO_BROKER": (80.0, "Virtual Asset Service Provider (VASP) / Crypto broker / Trader"),
    "ARMS_DEALER": (95.0, "Defense / Arms / Dual-use goods dealer"),
    "MSB_AGENT": (85.0, "Money Services Business (MSB) / Hawala / Remittance agent"),
    "PRECIOUS_METALS_DEALER": (75.0, "High-value commodities / Precious metals and gems dealer"),
    "SCRAP_METAL_MERCHANT": (70.0, "Scrap metal trading (VAT fraud / cash laundering vehicle)"),
    "OFFSHORE_TRUSTEE": (75.0, "Offshore company formation agent / Nominee director"),
    "POLITICIAN_SENIOR": (90.0, "Senior government official / Politically Exposed Person (PEP)"),
    "REAL_ESTATE_DEVELOPER_SPEC": (65.0, "Speculative real estate developer (layering risk)"),
}

# Medium Risk Occupations & Industry Sectors
MEDIUM_RISK_OCCUPATIONS: Dict[str, Tuple[float, str]] = {
    "USED_CAR_DEALER": (50.0, "Used car retail (cash intensive / vehicle export fraud)"),
    "NIGHTCLUB_RESTAURANT_OWNER": (45.0, "Cash-intensive hospitality / nightlife management"),
    "ART_ANTIQUES_DEALER": (55.0, "Fine art and antiques dealership (valuation subjectivity)"),
    "PAWNBROKER": (50.0, "Pawnbroking and collateral lending"),
    "IMPORT_EXPORT_TRADER": (50.0, "Independent cross-border import/export trading"),
    "INDEPENDENT_LEGAL_CONSULTANT": (40.0, "Sole legal practitioner handling client escrow/funds"),
    "LUXURY_CAR_BROKER": (50.0, "High-end luxury asset brokerage"),
    "CONSTRUCTION_CONTRACTOR": (40.0, "General construction contracting (subcontractor cash flows)"),
}

# Low Risk Occupations & Industry Sectors
LOW_RISK_OCCUPATIONS: Dict[str, Tuple[float, str]] = {
    "SOFTWARE_ENGINEER": (10.0, "Information technology / Software development"),
    "PHYSICIAN_DOCTOR": (10.0, "Licensed medical practitioner / Physician"),
    "NURSE": (10.0, "Healthcare worker / Registered nurse"),
    "TEACHER_PROFESSOR": (10.0, "Education / School teacher / University academic"),
    "ACCOUNTANT_CERTIFIED": (15.0, "Certified corporate accountant (regulated corporate employee)"),
    "CIVIL_SERVANT_JUNIOR": (15.0, "Junior administrative civil servant (non-PEP)"),
    "RETIRED_PENSIONER": (10.0, "Retired individual drawing state/pension funds"),
    "STUDENT": (15.0, "Full-time university student (subject to mule monitoring)"),
    "RETAIL_EMPLOYEE": (15.0, "Supermarket / Retail shop floor employee"),
    "CORPORATE_EXECUTIVE": (20.0, "Corporate corporate officer (regulated public firm)"),
    "MECHANIC": (15.0, "Automotive mechanic / Technician"),
}

def evaluate_occupation_risk(occupation_key: str) -> Tuple[str, float, str]:
    """
    Returns (risk_level, risk_score_0_to_100, description)
    """
    key = occupation_key.upper().strip()
    if key in HIGH_RISK_OCCUPATIONS:
        score, desc = HIGH_RISK_OCCUPATIONS[key]
        return ("HIGH", score, desc)
    if key in MEDIUM_RISK_OCCUPATIONS:
        score, desc = MEDIUM_RISK_OCCUPATIONS[key]
        return ("MEDIUM", score, desc)
    if key in LOW_RISK_OCCUPATIONS:
        score, desc = LOW_RISK_OCCUPATIONS[key]
        return ("LOW", score, desc)
    return ("MEDIUM", 30.0, f"Standard unclassified profession ({key})")
