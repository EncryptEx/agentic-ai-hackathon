"""KYC, Demographic, Purpose, and Product risk scoring module."""

from typing import List, Tuple
from models.customer import CustomerProfile, PEPStatus, AdverseMedia, SanctionStatus
from models.risk_score import PillarScore
from config.jurisdictions import evaluate_country_risk
from config.occupations import evaluate_occupation_risk
from config.products import PRODUCT_RISK, CHANNEL_RISK, PURPOSE_RISK
from config.rules_config import RISK_PILLAR_WEIGHTS

class KYCScorer:
    """Scores customer demographic, KYC identity, purpose, and product risk."""

    def score_demographic_kyc(self, customer: CustomerProfile) -> PillarScore:
        """
        Pillar 1: Demographic, Citizenship, Residency, PEP, Adverse Media, Occupation.
        Weight: 0.30
        """
        factors: List[str] = []
        score_components: List[float] = []

        # 1. Primary Citizenship Risk
        c_level, c_score, c_reasons = evaluate_country_risk(customer.citizenship)
        score_components.append(c_score * 0.20)
        factors.append(f"Citizenship {customer.citizenship}: {c_level} risk ({c_score:.0f}/100)")

        # 2. Dual Citizenship (if present)
        if customer.dual_citizenship:
            dc_level, dc_score, _ = evaluate_country_risk(customer.dual_citizenship)
            score_components.append(dc_score * 0.10)
            factors.append(f"Dual Citizenship {customer.dual_citizenship}: {dc_level} risk")
        else:
            score_components.append(c_score * 0.05)

        # 3. Residence Country Risk & Cross-Border Mismatch
        r_level, r_score, _ = evaluate_country_risk(customer.residence_country)
        score_components.append(r_score * 0.15)
        if customer.residence_country != customer.citizenship:
            factors.append(f"Cross-border resident (Lives in {customer.residence_country}, Citizen of {customer.citizenship})")
            score_components.append(15.0 * 0.05)
        else:
            factors.append(f"Domestic resident in {customer.residence_country}")

        # 4. Tax Residence Discrepancy
        if customer.tax_residence_country not in [customer.residence_country, customer.citizenship]:
            factors.append(f"Offshore tax residence mismatch: {customer.tax_residence_country}")
            score_components.append(30.0 * 0.05)

        # 5. PEP Screening Status
        pep_score = 0.0
        if customer.pep_status == PEPStatus.FOREIGN_PEP:
            pep_score = 90.0
            factors.append("CRITICAL: Designated Foreign PEP (Statutory Enhanced Due Diligence required)")
        elif customer.pep_status == PEPStatus.DOMESTIC_PEP:
            pep_score = 70.0
            factors.append("HIGH: Designated Domestic PEP (Senior public official oversight)")
        elif customer.pep_status == PEPStatus.PEP_ASSOCIATE:
            pep_score = 60.0
            factors.append("MEDIUM-HIGH: Close associate / family member of PEP")
        else:
            factors.append("PEP Screening: Clean (No political exposure identified)")
        score_components.append(pep_score * 0.30)

        # 6. Adverse Media
        media_score = 0.0
        if customer.adverse_media == AdverseMedia.FINANCIAL_CRIME:
            media_score = 95.0
            factors.append(f"CRITICAL: Adverse media match for Financial Crime ({customer.adverse_media_details or ''})")
        elif customer.adverse_media in [AdverseMedia.CORRUPTION_BRIBERY, AdverseMedia.FRAUD]:
            media_score = 80.0
            factors.append(f"HIGH: Adverse media match for {customer.adverse_media.value}")
        elif customer.adverse_media == AdverseMedia.REGULATORY_ENFORCEMENT:
            media_score = 60.0
            factors.append("MEDIUM-HIGH: Regulatory enforcement history noted")
        else:
            factors.append("Adverse Media: Clean (No derogatory news)")
        score_components.append(media_score * 0.30)

        # 7. Sanctions Hit (Override trigger handled in master engine too)
        if customer.sanction_status == SanctionStatus.CONFIRMED_HIT:
            factors.append("CRITICAL: Confirmed Sanctions / Watchlist hit")
            score_components.append(100.0 * 0.35)
        elif customer.sanction_status == SanctionStatus.FALSE_POSITIVE_RESOLVED:
            factors.append("Sanctions: False positive flagged and resolved during onboarding")
            score_components.append(15.0 * 0.05)

        # 8. Occupation & Industry Risk
        occ_level, occ_score, occ_desc = evaluate_occupation_risk(customer.occupation_risk_key)
        score_components.append(occ_score * 0.20)
        factors.append(f"Occupation {customer.occupation}: {occ_level} risk ({occ_desc})")

        # Combine components: take the max risk driver blended with aggregate components
        max_driver = max(c_score, r_score, pep_score, media_score, occ_score)
        agg_score = sum(score_components)
        raw_score = min(100.0, max(0.0, (max_driver * 0.60) + (agg_score * 0.40)))
        weight = RISK_PILLAR_WEIGHTS["CUSTOMER_KYC"]

        return PillarScore(
            pillar_name="Customer KYC & Demographics",
            weight=weight,
            raw_score=round(raw_score, 2),
            weighted_score=round(raw_score * weight, 2),
            contributing_factors=factors
        )

    def score_purpose_and_nature(self, customer: CustomerProfile) -> PillarScore:
        """
        Pillar 2: Declared purpose and nature of relationship & wealth plausibility.
        Weight: 0.15
        """
        factors: List[str] = []
        score_components: List[float] = []

        # 1. Declared Purpose Risk
        purpose_key = customer.declared_purpose_nature
        if purpose_key in PURPOSE_RISK:
            p_score, p_desc = PURPOSE_RISK[purpose_key]
            score_components.append(p_score * 0.50)
            factors.append(f"Account Purpose: {purpose_key} ({p_desc}) - Inherent risk: {p_score:.0f}/100")
        else:
            score_components.append(30.0 * 0.50)
            factors.append(f"Account Purpose: {purpose_key}")

        # 2. Source of Wealth & Funds Plausibility
        factors.append(f"Source of Funds: '{customer.source_of_funds}' | Source of Wealth: '{customer.source_of_wealth}'")
        
        # Plausibility check: declared net worth vs annual income
        if customer.annual_income_usd > 0:
            wealth_ratio = customer.net_worth_usd / customer.annual_income_usd
            if wealth_ratio > 12.0 and "Inheritance" not in customer.source_of_wealth and "Trust" not in customer.source_of_wealth:
                score_components.append(50.0 * 0.30)
                factors.append(f"Plausibility Note: Net worth ({customer.net_worth_usd:,.0f} USD) is {wealth_ratio:.1f}x annual income ({customer.annual_income_usd:,.0f} USD) - Requires wealth substantiation")
            else:
                score_components.append(15.0 * 0.30)
                factors.append("Wealth-to-Income ratio within plausible bounds")
        else:
            score_components.append(40.0 * 0.30)
            factors.append("Zero declared formal employment income")

        # 3. Expected Turnover Plausibility
        monthly_income = customer.annual_income_usd / 12.0
        if monthly_income > 0:
            turnover_ratio = customer.declared_expected_monthly_turnover_usd / monthly_income
            if turnover_ratio > 4.0:
                score_components.append(55.0 * 0.20)
                factors.append(f"High declared turnover relative to salary ({turnover_ratio:.1f}x monthly income)")
            else:
                score_components.append(10.0 * 0.20)
                factors.append("Declared expected monthly turnover aligns with income baseline")
        else:
            score_components.append(30.0 * 0.20)

        raw_score = min(100.0, max(0.0, sum(score_components)))
        weight = RISK_PILLAR_WEIGHTS["PURPOSE_NATURE"]

        return PillarScore(
            pillar_name="Purpose & Nature of Relationship",
            weight=weight,
            raw_score=round(raw_score, 2),
            weighted_score=round(raw_score * weight, 2),
            contributing_factors=factors
        )

    def score_products_and_channels(self, customer: CustomerProfile) -> PillarScore:
        """
        Pillar 3: Products held and onboarding channel risk.
        Weight: 0.15
        """
        factors: List[str] = []
        
        # 1. Product Inherent Risk
        product_scores = []
        for p in customer.products_held:
            if p in PRODUCT_RISK:
                p_val, p_desc = PRODUCT_RISK[p]
                product_scores.append(p_val)
                factors.append(f"Product: {p} ({p_desc}) - Risk: {p_val:.0f}/100")
            else:
                product_scores.append(20.0)
                factors.append(f"Product: {p}")

        max_prod_score = max(product_scores) if product_scores else 20.0
        avg_prod_score = (sum(product_scores) / len(product_scores)) if product_scores else 20.0
        
        # Blended product risk: 70% highest product risk + 30% average product risk
        blended_prod_score = (max_prod_score * 0.70) + (avg_prod_score * 0.30)

        # 2. Onboarding Channel Risk
        channel_key = customer.onboarding_channel
        if channel_key in CHANNEL_RISK:
            ch_score, ch_desc = CHANNEL_RISK[channel_key]
            factors.append(f"Onboarding Channel: {channel_key} ({ch_desc}) - Channel risk: {ch_score:.0f}/100")
        else:
            ch_score = 30.0
            factors.append(f"Onboarding Channel: {channel_key}")

        raw_score = (blended_prod_score * 0.65) + (ch_score * 0.35)
        raw_score = min(100.0, max(0.0, raw_score))
        weight = RISK_PILLAR_WEIGHTS["PRODUCTS_CHANNELS"]

        return PillarScore(
            pillar_name="Products & Onboarding Channels",
            weight=weight,
            raw_score=round(raw_score, 2),
            weighted_score=round(raw_score * weight, 2),
            contributing_factors=factors
        )
