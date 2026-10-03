"""Jurisdiction risk reference data based on FATF recommendations and global AML standards."""

from typing import Dict, Tuple, List

# FATF High-Risk Jurisdictions subject to a Call for Action (Blacklist)
FATF_BLACKLIST: Dict[str, str] = {
    "KP": "Democratic People's Republic of Korea (North Korea) - Sanctions / FATF Call for Action",
    "IR": "Iran - FATF Call for Action / Comprehensive Sanctions",
    "MM": "Myanmar - FATF Call for Action (Severe AML/CFT Deficiencies)",
}

# FATF Jurisdictions under Increased Monitoring (Greylist) - Sample active list
FATF_GREYLIST: Dict[str, str] = {
    "SY": "Syria - High risk of TF and ongoing conflict",
    "YE": "Yemen - TF risk and institutional breakdown",
    "HT": "Haiti - Strategic AML/CFT deficiencies",
    "SS": "South Sudan - Institutional weakness and high corruption risk",
    "ML": "Mali - Terrorism financing risk",
    "CD": "Democratic Republic of the Congo - Resource conflict & TF risk",
    "NG": "Nigeria - Increased AML/CFT monitoring",
    "MZ": "Mozambique - TF risks in northern region",
    "BF": "Burkina Faso - Terrorism financing risk",
    "SN": "Senegal - Strategic AML deficiencies",
    "VN": "Vietnam - Greylist monitoring for proliferation financing",
}

# Offshore Tax Havens & High-Secrecy Financial Centres
SECRECY_OFFSHORE: Dict[str, str] = {
    "KY": "Cayman Islands - Offshore secrecy & fund conduit risk",
    "VG": "British Virgin Islands - High corporate secrecy / shell conduit",
    "PA": "Panama - Offshore financial centre and canal transit hub",
    "VU": "Vanuatu - Low regulatory oversight / passport by investment",
    "SC": "Seychelles - Offshore IBC jurisdiction",
    "BZ": "Belize - High secrecy banking hub",
    "BS": "Bahamas - Offshore financial sector",
    "CW": "Curaçao - Online gambling & offshore licensing hub",
    "GI": "Gibraltar - Offshore gambling and crypto licensing",
}

# Moderate / Medium Risk Jurisdictions (Regional transshipment, moderate corruption index)
MEDIUM_RISK_COUNTRIES: Dict[str, str] = {
    "TR": "Turkey - Regional transshipment hub",
    "MX": "Mexico - Cartel proceeds and cash economy risk",
    "BR": "Brazil - High corruption perception in public procurement",
    "ZA": "South Africa - State capture investigations / greylist recovery",
    "IN": "India - Cash-intensive domestic market, Hawala corridors",
    "ID": "Indonesia - Southeast Asian regional cash flows",
    "TH": "Thailand - Cross-border gambling and unregulated border trade",
    "PH": "Philippines - Casino junkets and POGO legacy risks",
    "PK": "Pakistan - Cross-border remittance monitoring",
    "KE": "Kenya - Mobile money transshipment corridor",
    "CO": "Colombia - Narcotics trafficking proceeds risk",
}

# Low Risk Jurisdictions (OECD / FATF compliant with robust AML frameworks)
LOW_RISK_COUNTRIES: Dict[str, str] = {
    "US": "United States",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "CA": "Canada",
    "JP": "Japan",
    "AU": "Australia",
    "CH": "Switzerland",
    "SG": "Singapore",
    "NL": "Netherlands",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "NZ": "New Zealand",
    "IE": "Ireland",
    "FI": "Finland",
    "AT": "Austria",
    "BE": "Belgium",
    "ES": "Spain",
    "IT": "Italy",
    "AE": "United Arab Emirates",
}

def evaluate_country_risk(country_code: str) -> Tuple[str, float, List[str]]:
    """
    Returns (risk_level, risk_score_0_to_100, reasons)
    Risk levels: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    """
    cc = country_code.upper().strip()
    reasons = []

    if cc in FATF_BLACKLIST:
        reasons.append(FATF_BLACKLIST[cc])
        return ("CRITICAL", 100.0, reasons)

    if cc in FATF_GREYLIST:
        reasons.append(FATF_GREYLIST[cc])
        return ("HIGH", 75.0, reasons)

    if cc in SECRECY_OFFSHORE:
        reasons.append(SECRECY_OFFSHORE[cc])
        return ("HIGH", 65.0, reasons)

    if cc in MEDIUM_RISK_COUNTRIES:
        reasons.append(MEDIUM_RISK_COUNTRIES[cc])
        return ("MEDIUM", 40.0, reasons)

    if cc in LOW_RISK_COUNTRIES:
        reasons.append(f"FATF/OECD member with robust AML framework ({LOW_RISK_COUNTRIES[cc]})")
        return ("LOW", 10.0, reasons)

    # Default fallback for unlisted countries
    reasons.append(f"Standard non-FATF member country ({cc})")
    return ("MEDIUM", 35.0, reasons)
