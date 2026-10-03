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

"""Unified FastAPI application combining Google ADK Agents, A2A RPC, REST APIs, and Web UI."""

from __future__ import annotations

import contextlib
from datetime import datetime
import json
import os
from collections.abc import AsyncIterator
from typing import Any, Dict, Optional

from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from pydantic import BaseModel

from app.alert_feed import AlertDispatcher
from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from generator.customer_generator import ARCHETYPE_CONFIGS, CustomerGenerator
from generator.scenarios import (
    inject_account_takeover_scenario,
    inject_app_scam_scenario,
    inject_bust_out_fraud_scenario,
    inject_card_fraud_testing_scenario,
    inject_dormancy_burst_scenario,
    inject_money_mule_scenario,
    inject_sanction_corridor_scenario,
    inject_structuring_scenario,
    inject_sim_swap_scenario,
    inject_friendly_fraud_scenario,
    inject_bin_attack_scenario,
    inject_bec_impersonation_scenario,
    inject_aitm_session_hijack_scenario,
    inject_overpayment_scam_scenario,
    inject_tbml_scenario,
    inject_fan_out_layering_scenario,
    inject_cuckoo_smurfing_scenario,
    inject_crypto_mixer_scenario,
    inject_human_trafficking_scenario,
    inject_loan_wash_scenario,
)
from generator.transaction_generator import TransactionGenerator
from engine.risk_engine import RiskEngine
from models.customer import AdverseMedia, CustomerProfile, PEPStatus, SanctionStatus
from models.transaction import Transaction, TransactionDirection, TransactionType
from storage.database import DatabaseManager

load_dotenv()
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else ["*"]
)
otel_to_cloud = False

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(AGENT_DIR, "web", "static")
EXPORTS_DIR = os.path.join(AGENT_DIR, "exports")
VISUALIZATION_PATH = os.path.join(AGENT_DIR, "web", "visualization.html")
SENTINEL_PATH = os.path.join(AGENT_DIR, "Financialcrime.html")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=otel_to_cloud,
    lifespan=lifespan,
)
app.title = "Financial Crime Investigation Platform (FRAML)"
app.description = "API and Autonomous Multi-Agent System for KYC, AML, & Fraud Compliance"


# --------------------------------------------------------------------------
# REST API Endpoints (Data & Analytics)
# --------------------------------------------------------------------------

@app.get("/api/portfolio")
async def get_portfolio():
    """Retrieve portfolio risk distribution, AML and Fraud alert totals."""
    db = DatabaseManager()
    return db.get_portfolio_summary()


@app.get("/api/customers")
async def get_customers(
    tier: Optional[str] = None,
    q: Optional[str] = None
):
    """Retrieve all customers with optional tier and text filtering."""
    db = DatabaseManager()
    customers = db.get_all_customers_with_assessments()

    if tier and tier.upper() != "ALL":
        customers = [c for c in customers if (c.get("risk_tier") or "").upper() == tier.upper()]

    if q:
        q_lower = q.lower().strip()
        customers = [
            c for c in customers
            if q_lower in (c.get("first_name") or "").lower()
            or q_lower in (c.get("last_name") or "").lower()
            or q_lower in (c.get("customer_id") or "").lower()
            or q_lower in (c.get("citizenship") or "").lower()
            or q_lower in (c.get("occupation") or "").lower()
            or q_lower in (c.get("archetype") or "").lower()
        ]

    return {"total": len(customers), "customers": customers}


@app.get("/api/customer")
async def get_customer(id: str = Query(..., description="Customer ID, e.g. CUST-00015")):
    """Retrieve complete 360 customer dossier: KYC, assessment, transactions, and alerts."""
    db = DatabaseManager()
    dossier = db.get_customer_360(id.upper().strip())
    if not dossier:
        raise HTTPException(status_code=404, detail=f"Customer {id!r} not found.")
    return dossier


@app.get("/api/transactions")
async def get_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: Optional[str] = None,
    search: Optional[str] = None,
    dir: Optional[str] = None,
    direction: str = Query("ALL"),
    fraud_only: bool = False,
    aml_only: bool = False,
    customer_id: Optional[str] = None
):
    """Paged search and filtering over transaction streams."""
    db = DatabaseManager()
    active_search = q or search
    active_direction = dir or direction
    return db.query_transactions(
        page=page,
        page_size=page_size,
        search=active_search,
        direction=active_direction,
        fraud_only=fraud_only,
        aml_only=aml_only,
        customer_id=customer_id
    )


@app.get("/api/alerts")
async def get_alerts(
    type: Optional[str] = None,
    alert_type: str = Query("ALL"),
    severity: Optional[str] = None,
    customer_id: Optional[str] = None
):
    """Filter triggered AML and Fraud alerts."""
    db = DatabaseManager()
    active_type = type or alert_type
    alerts = db.query_alerts(
        alert_type=active_type,
        severity=severity,
        customer_id=customer_id
    )
    return {"total": len(alerts), "alerts": alerts}


@app.get("/api/archetypes")
async def get_archetypes():
    """List available retail customer archetypes."""
    return list(ARCHETYPE_CONFIGS.keys())


@app.get("/api/download")
async def download_file(file: str = Query(..., description="File name in exports/")):
    """Download CSV tabular export files."""
    safe_name = os.path.basename(file)
    file_path = os.path.join(EXPORTS_DIR, safe_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Export file {safe_name!r} not found.")
    return FileResponse(file_path, media_type="text/csv", filename=safe_name)


@app.post("/api/simulate")
async def simulate_customer_risk(payload: Dict[str, Any]):
    """Real-time FRAML risk engine simulation with optional typology injection."""
    engine = RiskEngine()
    cust_data = payload.get("customer", {})

    try:
        customer = CustomerProfile(
            customer_id=cust_data.get("customer_id", "SIM-001"),
            first_name=cust_data.get("first_name", "Test"),
            last_name=cust_data.get("last_name", "User"),
            date_of_birth=cust_data.get("date_of_birth", "1985-05-15"),
            age=int(cust_data.get("age", 40)),
            citizenship=cust_data.get("citizenship", "US"),
            dual_citizenship=cust_data.get("dual_citizenship"),
            residence_country=cust_data.get("residence_country", "US"),
            tax_residence_country=cust_data.get("tax_residence_country", "US"),
            address_city=cust_data.get("address_city", "New York"),
            address_postal_code=cust_data.get("address_postal_code", "10001"),
            address_line=cust_data.get("address_line", "100 Broadway"),
            occupation=cust_data.get("occupation", "Software Engineer"),
            occupation_risk_key=cust_data.get("occupation_risk_key", "SOFTWARE_ENGINEER"),
            industry=cust_data.get("industry", "Technology"),
            employer_name=cust_data.get("employer_name", "Tech Corp"),
            source_of_funds=cust_data.get("source_of_funds", "Salary"),
            source_of_wealth=cust_data.get("source_of_wealth", "Savings"),
            annual_income_usd=float(cust_data.get("annual_income_usd", 120000)),
            net_worth_usd=float(cust_data.get("net_worth_usd", 350000)),
            declared_expected_monthly_turnover_usd=float(cust_data.get("declared_expected_monthly_turnover_usd", 8000)),
            declared_expected_max_single_tx_usd=float(cust_data.get("declared_expected_max_single_tx_usd", 3000)),
            declared_purpose_nature=cust_data.get("declared_purpose_nature", "SALARY_AND_LIVING_EXPENSES"),
            onboarding_channel=cust_data.get("onboarding_channel", "DIGITAL_EKYC_BIOMETRIC"),
            onboarding_date=cust_data.get("onboarding_date", "2025-01-01"),
            products_held=cust_data.get("products_held", ["CURRENT_ACCOUNT"]),
            pep_status=PEPStatus(cust_data.get("pep_status", "NONE")),
            adverse_media=AdverseMedia(cust_data.get("adverse_media", "NONE")),
            sanction_status=SanctionStatus(cust_data.get("sanction_status", "CLEAN")),
            email_address=cust_data.get("email_address"),
            email_domain_type=cust_data.get("email_domain_type", "PUBLIC_FREE"),
            phone_number=cust_data.get("phone_number"),
            phone_line_type=cust_data.get("phone_line_type", "MOBILE"),
            device_primary_id=cust_data.get("device_primary_id", "DEV-SIM-PRIMARY"),
            primary_ip_address=cust_data.get("primary_ip_address", "192.168.1.1"),
            primary_ip_country=cust_data.get("primary_ip_country", cust_data.get("residence_country", "US")),
            synthetic_identity_score=float(cust_data.get("synthetic_identity_score", 10.0)),
            synthetic_id_indicators=cust_data.get("synthetic_id_indicators", []),
            archetype=cust_data.get("archetype", "CUSTOM_SIMULATION")
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid simulation customer profile: {e}")

    txs_data = payload.get("transactions", [])
    transactions = []
    for i, t in enumerate(txs_data):
        transactions.append(Transaction(
            transaction_id=t.get("transaction_id", f"SIM-TXN-{i+1:04d}"),
            customer_id=customer.customer_id,
            timestamp=t.get("timestamp", "2026-09-01T12:00:00"),
            transaction_type=TransactionType(t.get("transaction_type", "ACH_DEPOSIT")),
            direction=TransactionDirection(t.get("direction", "INBOUND")),
            amount_usd=float(t.get("amount_usd", 1000.0)),
            counterparty_name=t.get("counterparty_name", "Counterparty"),
            counterparty_country=t.get("counterparty_country", "US"),
            counterparty_category=t.get("counterparty_category", "RETAILER"),
            channel=t.get("channel", "ACH"),
            reference_narrative=t.get("reference_narrative", "Simulation Transaction"),
            device_id=t.get("device_id", customer.device_primary_id),
            ip_address=t.get("ip_address", customer.primary_ip_address),
            ip_country=t.get("ip_country", customer.primary_ip_country),
            card_entry_mode=t.get("card_entry_mode"),
            auth_status=t.get("auth_status", "AUTHORIZED"),
            is_new_payee=bool(t.get("is_new_payee", False)),
            is_fraud_synthetic=bool(t.get("is_fraud_synthetic", False)),
            fraud_typology_tag=t.get("fraud_typology_tag"),
            is_suspicious_synthetic=bool(t.get("is_suspicious_synthetic", False)),
            synthetic_typology_tag=t.get("synthetic_typology_tag")
        ))

    scenario = payload.get("scenario")
    # If no transactions were explicitly sent, or if scenario injection is requested and transactions is empty:
    if scenario and len(transactions) == 0:
        sc_upper = scenario.upper()
        tx_counter = 1
        now = datetime.now()
        if sc_upper == "ATO":
            transactions.extend(inject_account_takeover_scenario(customer, now, tx_counter))
        elif sc_upper == "CARD_TEST":
            transactions.extend(inject_card_fraud_testing_scenario(customer, now, tx_counter))
        elif sc_upper == "APP_SCAM":
            transactions.extend(inject_app_scam_scenario(customer, now, tx_counter))
        elif sc_upper == "BUSTOUT":
            transactions.extend(inject_bust_out_fraud_scenario(customer, now, tx_counter))
        elif sc_upper == "SIM_SWAP":
            transactions.extend(inject_sim_swap_scenario(customer, now, tx_counter))
        elif sc_upper == "FRIENDLY_FRAUD":
            transactions.extend(inject_friendly_fraud_scenario(customer, now, tx_counter))
        elif sc_upper == "BIN_ATTACK":
            transactions.extend(inject_bin_attack_scenario(customer, now, tx_counter))
        elif sc_upper == "BEC":
            transactions.extend(inject_bec_impersonation_scenario(customer, now, tx_counter))
        elif sc_upper == "AITM":
            transactions.extend(inject_aitm_session_hijack_scenario(customer, now, tx_counter))
        elif sc_upper == "OVERPAYMENT":
            transactions.extend(inject_overpayment_scam_scenario(customer, now, tx_counter))
        elif sc_upper == "STRUCTURING":
            transactions.extend(inject_structuring_scenario(customer, now, tx_counter))
        elif sc_upper == "MULE":
            transactions.extend(inject_money_mule_scenario(customer, now, tx_counter))
        elif sc_upper == "BLACKLIST":
            transactions.extend(inject_sanction_corridor_scenario(customer, now, tx_counter))
        elif sc_upper == "DORMANCY":
            transactions.extend(inject_dormancy_burst_scenario(customer, now, tx_counter))
        elif sc_upper == "TBML":
            transactions.extend(inject_tbml_scenario(customer, now, tx_counter))
        elif sc_upper == "FAN_OUT":
            transactions.extend(inject_fan_out_layering_scenario(customer, now, tx_counter))
        elif sc_upper == "CUCKOO":
            transactions.extend(inject_cuckoo_smurfing_scenario(customer, now, tx_counter))
        elif sc_upper == "MIXER":
            transactions.extend(inject_crypto_mixer_scenario(customer, now, tx_counter))
        elif sc_upper == "TRAFFICKING":
            transactions.extend(inject_human_trafficking_scenario(customer, now, tx_counter))
        elif sc_upper == "LOAN_WASH":
            transactions.extend(inject_loan_wash_scenario(customer, now, tx_counter))

    assessment = engine.evaluate_customer(customer, transactions)
    return assessment.model_dump()


@app.get("/api/typologies")
async def get_typologies():
    """List all available Fraud and AML typologies with metadata, category, and default profile presets."""
    return {
        "fraud_typologies": [
            {
                "id": "ATO", "code": "FR-01", "name": "Account Takeover (ATO) & Impossible Travel",
                "severity": "CRITICAL", "description": "Foreign proxy web session drains funds within 45 mins of legitimate local POS session.",
                "indicators": ["Device ID mismatch", "Impossible travel velocity (>900 km/h)", "Urgent offshore crypto drain"]
            },
            {
                "id": "CARD_TEST", "code": "FR-02", "name": "Card Testing & High-Dollar CNP Drain",
                "severity": "HIGH", "description": "Micro-authorization probes ($0.89, $1.45) followed by $3,450 luxury e-comm drain attempt.",
                "indicators": ["Sub-$3 digital charges", "Automated gateway testing", "Rapid four-figure drain attempt"]
            },
            {
                "id": "APP_SCAM", "code": "FR-03", "name": "Authorized Push Payment (APP) / Investment Scam",
                "severity": "HIGH", "description": "Social engineering / crypto investment scam coercing victim to push high-value wires to new payees.",
                "indicators": ["Urgent investment guarantee narrative", "First-time beneficiary", "P2P instant dissipation"]
            },
            {
                "id": "BUSTOUT", "code": "FR-04", "name": "First-Party Bust-Out & Deposit Kiting",
                "severity": "CRITICAL", "description": "Unverified inbound ACH deposit immediately followed by maximal ATM cash extractions before ACH returns.",
                "indicators": ["Inbound clearing window race condition", "Repetitive ATM daily max withdrawals", "Overdraft abandon"]
            },
            {
                "id": "SIM_SWAP", "code": "FR-06", "name": "SIM Swap & Outbound Wire Evacuation",
                "severity": "CRITICAL", "description": "Unauthorized mobile carrier port/SIM swap, immediate password reset, and large wire drain.",
                "indicators": ["Carrier port signal", "Immediate beneficiary addition", "Re-enrolled mobile device"]
            },
            {
                "id": "FRIENDLY_FRAUD", "code": "FR-07", "name": "Friendly Fraud / Systematic Chargeback Abuse",
                "severity": "HIGH", "description": "Repeated claims of non-receipt or stolen card despite legitimate primary device, IP, and 3DS verification.",
                "indicators": ["Repetitive high-value merchant disputes", "Trusted domestic home IP", "Delivered luxury tech merchandise"]
            },
            {
                "id": "BIN_ATTACK", "code": "FR-08", "name": "Automated BIN Attack & Card Testing Velocity",
                "severity": "CRITICAL", "description": "Botnet firing sequential authorizations with incrementing CVV/expiry combinations.",
                "indicators": ["High decline rate (>75%)", "Invalid CVV/expiry cluster", "Automated headless browser headers"]
            },
            {
                "id": "BEC", "code": "FR-09", "name": "Business Email Compromise (BEC) & Executive Impersonation",
                "severity": "CRITICAL", "description": "High-value wire diversion spoofing executive authority for strictly confidential M&A acquisition.",
                "indicators": ["Urgent executive acquisition narrative", "Offshore nominee counterparty", "Sudden banking details diversion"]
            },
            {
                "id": "AITM", "code": "FR-10", "name": "Adversary-in-the-Middle (AitM) Phishing Session Hijack",
                "severity": "CRITICAL", "description": "Reverse-proxy phishing kit steals session token, replayed from VPN proxy to bypass MFA and drain account.",
                "indicators": ["Session token replay", "Anomalous hosting ASN", "Immediate balance liquidation without credential change"]
            },
            {
                "id": "OVERPAYMENT", "code": "FR-11", "name": "Counterfeit Overpayment & Urgent Refund Scam",
                "severity": "HIGH", "description": "Victim receives counterfeit check/ACH advance, pressured to refund excess to third party before it bounces.",
                "indicators": ["Inbound unverified check deposit", "Urgent third-party wire refund", "Recruitment/mystery shopper cover"]
            }
        ],
        "aml_typologies": [
            {
                "id": "STRUCTURING", "code": "TM-01", "name": "Currency Transaction Reporting (CTR) Structuring",
                "severity": "CRITICAL", "description": "Multiple cash deposits in the $8,500–$9,900 range within 14 days to evade $10,000 threshold.",
                "indicators": ["Just-below-threshold cash deposits", "Multiple branch tellers used", "Evasion of statutory CTR filing"]
            },
            {
                "id": "MULE", "code": "TM-02", "name": "Pass-Through Account / Rapid Movement of Funds (Money Mule)",
                "severity": "CRITICAL", "description": "Inbound corporate wire followed by immediate dissipation (>90%) within 24-48 hours to crypto.",
                "indicators": ["Inbound wire spike", ">90% rapid turnover to virtual asset ramp", "Student/low-income mule profile"]
            },
            {
                "id": "BLACKLIST", "code": "TM-05", "name": "FATF Blacklist / High-Risk Sanctions Corridor",
                "severity": "CRITICAL", "description": "Direct wire activity with entities located in FATF Call for Action or comprehensive sanctions regimes.",
                "indicators": ["Counterparty in Iran, Syria, North Korea", "Correspondent banking sanctions alert", "Mandatory freeze candidate"]
            },
            {
                "id": "DORMANCY", "code": "TM-06", "name": "Dormant Account Reactivation Surge",
                "severity": "HIGH", "description": "Account with 60+ days zero activity suddenly reactivated with high-dollar incoming wires.",
                "indicators": ["Extended inactivity break", "Unexplained five-figure wire surge", "Sudden change in transactional velocity"]
            },
            {
                "id": "TBML", "code": "TM-08", "name": "Trade-Based Money Laundering (TBML) & Over-Invoicing",
                "severity": "CRITICAL", "description": "High-value cross-border wires referencing commercial freight invoices and shipping consignments.",
                "indicators": ["Consignment invoice documentation", "Trade hubs in UAE, Hong Kong, Panama", "Incongruent with individual retail account"]
            },
            {
                "id": "FAN_OUT", "code": "TM-09", "name": "Fan-Out Layering / High-Velocity Fund Distribution",
                "severity": "CRITICAL", "description": "Single large inbound credit immediately fragmented into 5+ outbound transfers across beneficiaries.",
                "indicators": ["Rapid audit trail fragmentation", "Disparate peer and crypto offramps", "Same-day dissipation"]
            },
            {
                "id": "CUCKOO", "code": "TM-10", "name": "Cuckoo Smurfing & Hawala Remittance Matching",
                "severity": "HIGH", "description": "Account receives multiple unrelated cash or domestic transfers from strangers to settle underground remittance.",
                "indicators": ["Multiple unconnected third-party remitters", "Cash deposits across disparate branches", "Underground Hawala integration"]
            },
            {
                "id": "MIXER", "code": "TM-11", "name": "Crypto Mixer & Anonymity Protocol Interaction",
                "severity": "CRITICAL", "description": "Direct financial interaction with sanctioned zero-knowledge mixers (Tornado Cash / Wasabi).",
                "indicators": ["Interaction with Tornado Cash / Sinbad", "Privacy pool obfuscation", "Source-of-funds concealment"]
            },
            {
                "id": "TRAFFICKING", "code": "TM-12", "name": "Human Trafficking & Labor Exploitation Red Flags",
                "severity": "CRITICAL", "description": "Centralized wage skimming from multiple workers, accompanied by late-night ATM cash drains in transit corridors.",
                "indicators": ["Centralized wage pooling from workers", "Late-night ATM cash withdrawals", "Transit motel & transport expenditures"]
            },
            {
                "id": "LOAN_WASH", "code": "TM-13", "name": "Loan Collateral Laundering & Rapid Early Liquidation",
                "severity": "HIGH", "description": "Loan disbursement disbursed and immediately liquidated early using unverified offshore/cash funds.",
                "indicators": ["Full early loan payoff within 30 days", "Repayment from unverified third-party funds", "Cash-to-clean-loan conversion"]
            }
        ]
    }


class GenerateRequest(BaseModel):
    count: int = 50
    days: int = 90
    seed: Optional[int] = None


@app.post("/api/generate")
async def generate_cohort(req: GenerateRequest):
    """Generate a new synthetic banking customer cohort and evaluate with 5-pillar engine."""
    cg = CustomerGenerator(seed=req.seed)
    tg = TransactionGenerator(seed=req.seed)
    engine = RiskEngine()
    db = DatabaseManager()

    customers = cg.generate_batch(count=req.count)
    tx_map = {}
    assessments = []

    for c in customers:
        c_txs = tg.generate_customer_transactions(c, days_history=req.days)
        tx_map[c.customer_id] = c_txs
        assessment = engine.evaluate_customer(c, c_txs)
        assessments.append(assessment)

    db.save_batch(customers, tx_map, assessments)
    return {
        "status": "success",
        "customers_generated": len(customers),
        "total_transactions": sum(len(t) for t in tx_map.values()),
        "total_alerts": sum(len(a.alerts) + len(a.fraud_alerts) for a in assessments),
    }


class InvestigateRequest(BaseModel):
    customer_id: str
    alert_id: Optional[str] = None


@app.post("/api/investigate")
async def investigate_customer(req: InvestigateRequest, request: Request):
    """Trigger the autonomous Google ADK multi-agent investigation pipeline for a customer."""
    from google.genai import types
    from app.alert_feed import (
        AlertDispatcher,
        generate_executive_summary_report,
        generate_specialist_investigation_report,
    )

    dispatcher = AlertDispatcher()
    cust_id = req.customer_id.upper().strip()

    try:
        packet = dispatcher.prepare_case_packet(cust_id, alert_id=req.alert_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    prompt = dispatcher.generate_investigation_prompt(cust_id, packet.get("trigger_alert"))

    runner: Optional[Runner] = getattr(request.app.state, "runner", None)
    adk_app_name = getattr(request.app.state, "agent_app_name", "app")
    final_report = ""

    # Attempt execution with Google ADK Runner & Gemini LLM
    if runner and runner.session_service:
        try:
            session = await runner.session_service.create_session(
                app_name=adk_app_name,
                user_id="compliance_dashboard"
            )
            new_message = types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)]
            )
            async for event in runner.run_async(
                user_id="compliance_dashboard",
                session_id=session.id,
                new_message=new_message,
            ):
                if hasattr(event, "content") and event.content and hasattr(event.content, "parts"):
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            final_report = part.text
        except Exception:
            # Fall back to specialist data tool synthesis if LLM credentials are unconfigured
            pass

    # Ensure full 11-section specialist investigation is produced
    if not final_report or not final_report.strip():
        final_report = generate_specialist_investigation_report(cust_id, trigger_alert=packet.get("trigger_alert"))

    # Also generate the concise executive summary for leadership review
    exec_summary = generate_executive_summary_report(cust_id, trigger_alert=packet.get("trigger_alert"))

    if req.alert_id and final_report:
        dispatcher.mark_alert_investigated(req.alert_id, notes=final_report[:500])

    # Log to immutable audit ledger with SHA-256 integrity hash
    db = DatabaseManager()
    inv_id = db.log_investigation({
        "customer_id": cust_id,
        "customer_name": packet.get("customer_name"),
        "trigger_alert_id": req.alert_id,
        "trigger_rule": (packet.get("trigger_alert") or {}).get("rule_name", "Manual Risk Review"),
        "risk_tier": packet.get("risk_tier"),
        "composite_score": packet.get("composite_score", 0.0),
        "model_version": "gemini-3.8-flash",
        "raw_prompt": prompt,
        "final_report_text": final_report,
        "officer_sign_off_status": "PENDING",
    })
    log_record = db.get_investigation_audit_log(inv_id)
    report_sha256 = log_record.get("final_report_sha256") if log_record else ""

    return {
        "investigation_id": inv_id,
        "report_sha256": report_sha256,
        "officer_sign_off_status": "PENDING",
        "customer_id": cust_id,
        "customer_name": packet["customer_name"],
        "archetype": packet["archetype"],
        "risk_tier": packet["risk_tier"],
        "composite_score": packet["composite_score"],
        "prompt_dispatched": prompt,
        "report": final_report,
        "executive_summary": exec_summary,
    }


@app.post("/api/investigate/executive-summary")
async def investigate_customer_executive_summary(req: InvestigateRequest, request: Request):
    """Run Executive Summary Agent for rapid human compliance decision-making without the full dossier."""
    from app.alert_feed import AlertDispatcher, generate_executive_summary_report

    dispatcher = AlertDispatcher()
    cust_id = req.customer_id.upper().strip()

    try:
        packet = dispatcher.prepare_case_packet(cust_id, alert_id=req.alert_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    summary_prompt = (
        f"Provide a concise Executive Summary (BLUF, risk scores, red flags, "
        f"exposure, and immediate recommendations) for customer {cust_id} "
        f"({packet.get('customer_name')}) for a human compliance officer who does not want to read "
        f"the full multi-agent investigation."
    )

    exec_summary = generate_executive_summary_report(cust_id, trigger_alert=packet.get("trigger_alert"))

    if req.alert_id and exec_summary:
        dispatcher.mark_alert_investigated(req.alert_id, notes=exec_summary[:500])

    db = DatabaseManager()
    inv_id = db.log_investigation({
        "customer_id": cust_id,
        "customer_name": packet.get("customer_name"),
        "trigger_alert_id": req.alert_id,
        "trigger_rule": (packet.get("trigger_alert") or {}).get("rule_name", "Manual Risk Review"),
        "risk_tier": packet.get("risk_tier"),
        "composite_score": packet.get("composite_score", 0.0),
        "model_version": "gemini-3.8-flash",
        "raw_prompt": summary_prompt,
        "final_report_text": exec_summary,
        "officer_sign_off_status": "PENDING",
    })
    log_record = db.get_investigation_audit_log(inv_id)
    report_sha256 = log_record.get("final_report_sha256") if log_record else ""

    return {
        "investigation_id": inv_id,
        "report_sha256": report_sha256,
        "officer_sign_off_status": "PENDING",
        "customer_id": cust_id,
        "customer_name": packet["customer_name"],
        "archetype": packet["archetype"],
        "risk_tier": packet["risk_tier"],
        "composite_score": packet["composite_score"],
        "prompt_dispatched": summary_prompt,
        "report": exec_summary,
        "executive_summary": exec_summary,
    }


class SignOffRequest(BaseModel):
    investigation_id: str
    officer_name: str
    decision: str
    notes: Optional[str] = None
    action_taken: Optional[str] = None


@app.post("/api/investigations/sign-off")
async def sign_off_investigation(req: SignOffRequest):
    """Records human compliance officer sign-off and rationale for an investigation."""
    db = DatabaseManager()
    ok = db.update_audit_sign_off(
        investigation_id=req.investigation_id,
        officer_sign_off_status=req.decision,
        officer_name=req.officer_name,
        officer_notes=req.notes,
        officer_action_taken=req.action_taken or req.decision
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Investigation {req.investigation_id} not found")
    updated = db.get_investigation_audit_log(req.investigation_id)
    return {"status": "success", "audit_log": updated}


@app.get("/api/investigations/audit-trail")
async def get_audit_trail(customer_id: Optional[str] = None, limit: int = 50):
    """Retrieves immutable audit logs for compliance reviews, optionally filtered by customer."""
    db = DatabaseManager()
    return db.get_investigation_audit_logs(customer_id=customer_id, limit=limit)


@app.get("/api/investigations/{investigation_id}")
async def get_investigation_detail(investigation_id: str):
    """Retrieves a single investigation audit log and its SHA-256 integrity verification."""
    db = DatabaseManager()
    log = db.get_investigation_audit_log(investigation_id)
    if not log:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return log


# --------------------------------------------------------------------------
# Customer Outreach Video & Audio Call Endpoints (Anti-Tipping-Off)
# --------------------------------------------------------------------------

class StartCallRequest(BaseModel):
    customer_id: str
    alert_id: Optional[str] = None
    voice_name: Optional[str] = "Aoede"


class CallTurnRequest(BaseModel):
    session_id: str
    message: str
    voice_name: Optional[str] = "Aoede"
    interrupted: Optional[bool] = False


class AudioTurnRequest(BaseModel):
    session_id: str
    audio_base64: str
    audio_mime: Optional[str] = "audio/webm"
    voice_name: Optional[str] = "Aoede"
    interrupted: Optional[bool] = False


class CompleteCallRequest(BaseModel):
    session_id: str


class TTSRequest(BaseModel):
    text: str
    emotion: Optional[str] = "warm_reassuring"
    voice_name: Optional[str] = "Aoede"


@app.post("/api/call/start")
async def api_start_customer_call(req: StartCallRequest):
    """Initiates an interactive voice/video verification call with a customer under anti-tipping-off rules."""
    from app.customer_call_agent import start_customer_call
    try:
        voice = req.voice_name or "Aoede"
        greeting = start_customer_call(req.customer_id.upper().strip(), alert_id=req.alert_id, voice_name=voice)
        return greeting
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/call/turn")
async def api_customer_call_turn(req: CallTurnRequest):
    """Processes a conversational turn with the customer, updating plausibility and generating agent speech."""
    from app.customer_call_agent import process_call_turn
    try:
        voice = req.voice_name or "Aoede"
        result = process_call_turn(
            req.session_id,
            req.message.strip(),
            voice_name=voice,
            interrupted=bool(req.interrupted),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/call/audio-turn")
async def api_customer_call_audio_turn(req: AudioTurnRequest):
    """Processes a spoken audio turn from customer microphone using Gemini multimodal transcription."""
    from app.customer_call_agent import process_audio_turn
    import base64
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
        mime = req.audio_mime or "audio/webm"
        voice = req.voice_name or "Aoede"
        result = process_audio_turn(
            req.session_id,
            audio_bytes,
            mime_type=mime,
            voice_name=voice,
            interrupted=bool(req.interrupted),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/call/tts")
async def api_synthesize_call_tts(req: TTSRequest):
    """Generates expressive neural audio on-demand using Google Gemini Audio."""
    from app.customer_call_agent import CustomerCallSession
    session = CustomerCallSession("CUST-00019")
    audio_b64 = session.synthesize_speech(req.text, emotion=req.emotion or "warm_reassuring", voice_name=req.voice_name or "Aoede")
    if not audio_b64:
        raise HTTPException(status_code=500, detail="Neural audio synthesis unavailable")
    return {
        "audio_base64": audio_b64,
        "audio_mime": "audio/wav",
        "emotion": req.emotion or "warm_reassuring",
        "voice_name": req.voice_name or "Aoede",
    }


@app.post("/api/call/complete")
async def api_complete_customer_call(req: CompleteCallRequest):
    """Concludes the customer call, compiles formal interview dossier, and logs to audit ledger."""
    from app.customer_call_agent import complete_customer_call
    try:
        result = complete_customer_call(req.session_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/call/persona")
async def api_get_call_persona():
    """Returns metadata and configuration for the AI video agent persona."""
    return {
        "name": "Agent Claire Sterling",
        "title": "Senior Customer Verification & Account Security Specialist",
        "department": "Valiant Bank Client Care & Verification Unit",
        "badge_id": "VB-SEC-8419",
        "jurisdiction": "Global Banking Operations",
        "voice_gender": "female",
        "voice_pitch": 1.05,
        "voice_rate": 0.96,
        "model": "gemini-3.8-flash (Gemini Audio Reasoning)",
        "security_protocol": "Anti-Tipping-Off Safeguards Active (POCA §333A / BSA 31 U.S.C. §5318)",
    }


# --------------------------------------------------------------------------
# Web Dashboard & Visualizer
# --------------------------------------------------------------------------

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/style.css")
async def serve_style():
    """Serve style.css directly for root-level dashboard requests."""
    return FileResponse(os.path.join(STATIC_DIR, "style.css"), media_type="text/css")


@app.get("/app.js")
async def serve_app_js():
    """Serve app.js directly for root-level dashboard requests."""
    return FileResponse(os.path.join(STATIC_DIR, "app.js"), media_type="application/javascript")


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Interactive compliance monitoring dashboard."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Compliance Dashboard static files missing</h1>", status_code=404)


@app.get("/visualizer", response_class=HTMLResponse)
async def serve_visualizer():
    """FRAML Risk Visualizer with Chart.js analytics."""
    if os.path.exists(VISUALIZATION_PATH):
        with open(VISUALIZATION_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Visualizer file missing</h1>", status_code=404)


@app.get("/sentinel", response_class=HTMLResponse)
async def serve_sentinel():
    """Sentinel Nordic AML and Sanctions visualizer."""
    if os.path.exists(SENTINEL_PATH):
        with open(SENTINEL_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Sentinel file missing</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.fast_api_app:app", host="0.0.0.0", port=8000, reload=True)
