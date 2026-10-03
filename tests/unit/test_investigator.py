# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the Financial Crime Investigation system.

Tests cover:
- Synthetic data tools and SQL queries
- Typology detection (structuring, pass-through, clean baselines)
- Multi-agent architecture, specialist pipelines, and tool mappings
"""

import pytest

from app.agent import (
    consolidator_agent,
    customer_agent,
    fraud_agent,
    investigation_pipeline,
    ownership_agent,
    risk_agent,
    root_agent,
    transaction_agent,
)
from app.tools import (
    CUSTOMER_TOOLS,
    FRAUD_TOOLS,
    OWNERSHIP_TOOLS,
    RISK_TOOLS,
    TRANSACTION_TOOLS,
    analyze_transactions,
    get_country_risk,
    get_customer_profile,
    get_digital_telemetry,
    get_expected_activity,
    get_fraud_alerts,
    get_kyc_dossier,
    get_ownership_structure,
    get_risk_assessment,
    get_transaction_alerts,
    get_transactions,
    list_customers,
)


class TestInvestigationTools:
    """Tests for synthetic dataset tools used by specialist agents."""

    def test_list_customers(self) -> None:
        customers = list_customers()
        assert len(customers) == 100
        customer_ids = {c["customer_id"] for c in customers}
        assert "CUST-00001" in customer_ids
        assert "CUST-00002" in customer_ids
        assert "CUST-00015" in customer_ids
        assert "CUST-00019" in customer_ids

        for c in customers:
            assert "customer_id" in c
            assert "name" in c
            assert "type" in c
            assert "country" in c
            assert "risk_rating" in c

    def test_get_customer_profile_found(self) -> None:
        profile = get_customer_profile("CUST-00015")
        assert profile["customer_id"] == "CUST-00015"
        assert profile["name"] == "James Moran"
        assert profile["type"] == "individual"
        assert profile["country"] == "GB"
        assert profile["archetype"] == "STRUCTURING_CASH_OPERATOR"

    def test_get_customer_profile_not_found(self) -> None:
        profile = get_customer_profile("UNKNOWN_999")
        assert "error" in profile

    def test_get_expected_activity(self) -> None:
        expected = get_expected_activity("CUST-00015")
        assert expected["customer_id"] == "CUST-00015"
        assert expected["expected_monthly_volume"] == 8100.0

    def test_get_expected_activity_not_found(self) -> None:
        expected = get_expected_activity("UNKNOWN_999")
        assert "error" in expected

    def test_get_transactions_chronological(self) -> None:
        txns = get_transactions("CUST-00015")
        assert len(txns) > 0
        dates = [t["date"] for t in txns]
        assert dates == sorted(dates)

    def test_get_transactions_empty_customer(self) -> None:
        txns = get_transactions("UNKNOWN_999")
        assert txns == []

    def test_analyze_transactions_cust00015_structuring(self) -> None:
        """CUST-00015 must trigger structuring (TM-01) and volume alerts."""
        analysis = analyze_transactions("CUST-00015")
        assert analysis["customer_id"] == "CUST-00015"
        assert analysis["transaction_count"] > 0
        assert len(analysis["tm_alerts"]) > 0

        rule_ids = {a["rule_id"] for a in analysis["tm_alerts"]}
        assert "TM-01" in rule_ids

    def test_analyze_transactions_cust00002_clean_baseline(self) -> None:
        """CUST-00002 (Anthony Gonzalez) is clean baseline: zero TM alerts."""
        alerts = get_transaction_alerts("CUST-00002")
        assert len(alerts) == 0

    def test_get_ownership_structure(self) -> None:
        ownership = get_ownership_structure("CUST-00015")
        assert ownership["customer_id"] == "CUST-00015"
        assert len(ownership["shareholders"]) > 0
        assert ownership["shareholders"][0]["stake"] == 1.0

    def test_get_country_risk(self) -> None:
        panama = get_country_risk("PA")
        assert panama["country"] == "PA"
        assert panama["rating"] == "high"

        gb = get_country_risk("GB")
        assert gb["rating"] == "low"

        unknown = get_country_risk("Atlantis")
        assert "error" in unknown

    def test_get_kyc_dossier_core_and_retail(self) -> None:
        """Verify KYC CDD dossier extraction for retail customers."""
        dossier_cust15 = get_kyc_dossier("CUST-00015")
        assert dossier_cust15["customer_id"] == "CUST-00015"
        assert dossier_cust15["archetype"] == "STRUCTURING_CASH_OPERATOR"
        assert "demographics" in dossier_cust15
        assert "financial_and_wealth_plausibility" in dossier_cust15
        assert "screening_and_watchlists" in dossier_cust15

        dossier_cust1 = get_kyc_dossier("CUST-00001")
        assert dossier_cust1["customer_id"] == "CUST-00001"
        assert dossier_cust1["demographics"]["age"] > 0

    def test_get_transaction_alerts(self) -> None:
        """Verify transaction monitoring alerts are returned with rule metadata."""
        alerts_cust15 = get_transaction_alerts("CUST-00015")
        assert len(alerts_cust15) > 0
        rule_ids = {a["rule_id"] for a in alerts_cust15}
        assert "TM-01" in rule_ids  # Structuring

        for a in alerts_cust15:
            assert "alert_id" in a
            assert "rule_name" in a
            assert "severity" in a
            assert "summary" in a

    def test_get_risk_assessment(self) -> None:
        """Verify 4-pillar risk assessment scoring, tiers, and action checklist."""
        assessment_cust15 = get_risk_assessment("CUST-00015")
        assert assessment_cust15["customer_id"] == "CUST-00015"
        assert assessment_cust15["risk_tier"] == "CRITICAL"
        assert assessment_cust15["composite_score"] >= 85.0
        assert assessment_cust15["recommended_action"] == "FILE_SAR_AND_IMMEDIATE_ACCOUNT_RESTRICTION"
        assert len(assessment_cust15["action_checklist"]) > 0

        # Check 4 pillars
        pillars = assessment_cust15["pillars"]
        assert "kyc_demographics" in pillars
        assert "purpose_and_nature" in pillars
        assert "products_and_channels" in pillars
        assert "behavioral_transaction_monitoring" in pillars

        # Clean baseline customer CUST-00002
        assessment_cust2 = get_risk_assessment("CUST-00002")
        assert assessment_cust2["customer_id"] == "CUST-00002"
        assert assessment_cust2["risk_tier"] == "LOW"
        assert assessment_cust2["composite_score"] < 35.0


class TestAgentArchitecture:
    """Verifies the multi-agent hierarchy and tool assignments match the architecture."""

    def test_root_orchestrator(self) -> None:
        assert root_agent.name == "investigation_agent"
        assert len(root_agent.sub_agents) == 2
        assert root_agent.sub_agents[0] is investigation_pipeline
        assert root_agent.sub_agents[1] is consolidator_agent

    def test_investigation_pipeline_specialists(self) -> None:
        assert investigation_pipeline.name == "investigation_pipeline"
        assert len(investigation_pipeline.sub_agents) == 5

        specialist_names = [agent.name for agent in investigation_pipeline.sub_agents]
        assert "customer_agent" in specialist_names
        assert "transaction_agent" in specialist_names
        assert "fraud_agent" in specialist_names
        assert "ownership_agent" in specialist_names
        assert "risk_agent" in specialist_names

    def test_specialist_tool_mappings(self) -> None:
        """Verify each specialist agent has the exact tools assigned in the architecture."""
        assert customer_agent.tools == CUSTOMER_TOOLS
        assert set(customer_agent.tools) == {
            list_customers,
            get_customer_profile,
            get_expected_activity,
            get_kyc_dossier,
            get_digital_telemetry,
        }

        assert transaction_agent.tools == TRANSACTION_TOOLS
        assert set(transaction_agent.tools) == {
            get_transactions,
            analyze_transactions,
            get_expected_activity,
            get_transaction_alerts,
        }

        assert fraud_agent.tools == FRAUD_TOOLS
        assert set(fraud_agent.tools) == {
            get_fraud_alerts,
            get_digital_telemetry,
            get_transactions,
            get_customer_profile,
        }

        assert ownership_agent.tools == OWNERSHIP_TOOLS
        assert set(ownership_agent.tools) == {
            get_ownership_structure,
            get_country_risk,
        }

        assert risk_agent.tools == RISK_TOOLS
        assert set(risk_agent.tools) == {
            get_customer_profile,
            get_country_risk,
            get_ownership_structure,
            get_risk_assessment,
        }

    def test_synthetic_data_and_human_disclaimers(self) -> None:
        """Verify all agents enforce synthetic data and human-in-the-loop guardrails."""
        for agent in [
            customer_agent,
            transaction_agent,
            fraud_agent,
            ownership_agent,
            risk_agent,
            consolidator_agent,
        ]:
            assert "SYNTHETIC" in agent.instruction
            assert "human investigator" in agent.instruction.lower()

    def test_consolidator_case_overview(self) -> None:
        """Verify consolidator agent instructions require an executive Case Overview."""
        assert "- Case overview" in consolidator_agent.instruction
        assert "Case Identifier / Reference" in consolidator_agent.instruction
        assert "Investigation Trigger / Rationale" in consolidator_agent.instruction
        assert "Primary Typologies Identified" in consolidator_agent.instruction
        assert "Executive Synopsis" in consolidator_agent.instruction

    def test_investigation_audit_trail_and_sign_off(self) -> None:
        """Verify immutable audit logging, SHA-256 digest computation, and officer sign-off."""
        import hashlib
        from storage.database import DatabaseManager

        db = DatabaseManager()
        test_report = "Comprehensive 11-section FRAML investigation for CUST-00015"
        expected_sha = hashlib.sha256(test_report.encode("utf-8")).hexdigest()

        inv_id = db.log_investigation({
            "customer_id": "CUST-00015",
            "customer_name": "James Moran",
            "trigger_rule": "TM-01 Structuring",
            "risk_tier": "CRITICAL",
            "composite_score": 86.5,
            "final_report_text": test_report,
        })

        assert inv_id.startswith("INV-")
        log = db.get_investigation_audit_log(inv_id)
        assert log is not None
        assert log["customer_id"] == "CUST-00015"
        assert log["final_report_sha256"] == expected_sha
        assert log["officer_sign_off_status"] == "PENDING"

        # Update sign-off
        ok = db.update_audit_sign_off(
            investigation_id=inv_id,
            officer_sign_off_status="APPROVED_SAR_FILED",
            officer_name="Officer Jane",
            officer_notes="Confirmed structuring pattern",
        )
        assert ok is True

        updated = db.get_investigation_audit_log(inv_id)
        assert updated["officer_sign_off_status"] == "APPROVED_SAR_FILED"
        assert updated["officer_name"] == "Officer Jane"
        assert updated["officer_notes"] == "Confirmed structuring pattern"
        assert updated["reviewed_at"] is not None

    def test_framl_deterministic_eval_metric(self) -> None:
        """Verify the deterministic compliance metric evaluates section coverage and disclaimers."""
        from tests.eval.framl_metric import evaluate

        compliant_report = """
        # Case Overview
        Subject CUST-00015
        # Customer Overview
        # Key Observations
        # Transaction Patterns & AML Monitoring
        TM-01 Structuring alert
        # Fraud & Cybercrime Telemetry Findings
        # Ownership & Control Findings
        # Relevant Risk Indicators & FRAML Score
        # Evidence Supporting Each Finding
        # Contradictory or Mitigating Evidence
        # Missing Information
        # Suggested Next Investigative Questions
        # Overall Case Summary
        All data is synthetic and fictional. Human compliance officer decision required.
        """
        res = evaluate({"response": compliant_report})
        assert res["score"] >= 0.9
        assert "Synthetic guardrail: True" in res["explanation"]
        assert "HITL guardrail: True" in res["explanation"]

