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

"""AI Financial Crime & FRAML Investigation Agent — multi-agent suite.

Architecture
------------
root_agent (Investigation Agent / orchestrator)
├── investigation_pipeline (SequentialAgent)
│   ├── customer_agent      reviews profile, KYC CDD dossier, wealth plausibility
│   ├── transaction_agent   analyses transactions and flags AML anomalies (TM-01..07)
│   ├── fraud_agent         analyses device telemetry, impossible travel, and fraud typologies (FR-01..05)
│   ├── ownership_agent     analyses ownership, UBOs, and country risks
│   └── risk_agent          evaluates 5-pillar FRAML risk scores and statutory overrides
└── consolidator_agent      synthesizes specialist findings into an 11-section case file

ALL DATA IS SYNTHETIC AND FICTIONAL. This system provides analysis for human
compliance officers and investigators; it does not make autonomous legal decisions.
"""

import os
from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
if os.path.exists(_ENV_PATH):
    load_dotenv(_ENV_PATH)
load_dotenv()

try:
    from google.adk.agents import Agent, SequentialAgent
    from google.adk.apps import App
    from google.adk.models import Gemini
    from google.genai import types
    HAS_ADK = True
except ImportError:
    HAS_ADK = False
    class Agent:
        def __init__(self, *args, **kwargs): pass
    class SequentialAgent(Agent):
        def __init__(self, *args, **kwargs): pass
    class App:
        def __init__(self, *args, **kwargs): pass
    class Gemini:
        def __init__(self, *args, **kwargs): pass
    class types:
        class HttpRetryOptions:
            def __init__(self, *args, **kwargs): pass

from app.context_callbacks import after_model_usage, before_model_context

from app.tools import (
    CUSTOMER_TOOLS,
    FRAUD_TOOLS,
    OWNERSHIP_TOOLS,
    RISK_TOOLS,
    TRANSACTION_TOOLS,
)
from app.orchestrator.agent import arbiter_agent

MODEL = "gemini-3.8-flash"

# Shared guardrail text appended to every specialist instruction.
_SYNTHETIC_ONLY = (
    "All data you receive is SYNTHETIC and fictional. Never imply it is real. "
    "Report only what the tools return; do not invent facts, names, or numbers. "
    "You provide analysis for a human investigator — you do not make legal or "
    "regulatory decisions."
)


def _model() -> Gemini:
    """Build the shared Gemini model config for every agent in this app."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client_kwargs = {"api_key": api_key} if api_key else {}
    
    # If the user has provided an API key (e.g. for Google AI Studio),
    # ensure Vertex AI is disabled, otherwise google-genai throws credential errors
    # because it prioritizes Vertex AI config in the .env file.
    if api_key and os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"):
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
        
    return Gemini(
        model=MODEL,
        client_kwargs=client_kwargs,
        retry_options=types.HttpRetryOptions(attempts=3),
    )


# --------------------------------------------------------------------------
# Specialist agents
# --------------------------------------------------------------------------

customer_agent = Agent(
    name="customer_agent",
    description=(
        "Reviews a customer's profile, occupation, KYC CDD dossier, expected activity, "
        "wealth plausibility, and watchlist screening attributes. Use first to establish identity."
    ),
    model=_model(),
    before_model_callback=before_model_context,
    after_model_callback=after_model_usage,
    instruction=f"""You are the Customer Agent in a financial crime investigation.

   Your job: establish who the customer is, their KYC Customer Due Diligence (CDD) profile,
   wealth plausibility, and what activity is expected of them.

   Steps:
   1. Call `get_customer_profile` and `get_kyc_dossier` for the customer under investigation.
   2. Call `get_expected_activity` to retrieve their expected monthly profile.
   3. If the customer id is unknown, call `list_customers` to find it.

   Report back, concisely:
   - Customer overview (name, type, occupation, nationality/citizenship, residence, tax residence, onboarding date)
   - Stated risk rating and customer archetype
   - Wealth & income plausibility (annual income, net worth, wealth-to-income ratio, source of funds & wealth)
   - Expected activity profile (declared monthly turnover, max single transaction, stated purpose)
   - Watchlist & screening flags (PEP status & details, adverse media findings, sanctions matches)
   - Digital identity signals (synthetic identity score, burner email, VoIP phone flags)
   - Key CDD discrepancies or attributes warranting investigative attention

   {_SYNTHETIC_ONLY}
   """,
    tools=CUSTOMER_TOOLS,
    output_key="customer_findings",
)


transaction_agent = Agent(
    name="transaction_agent",
    description=(
        "Analyses transaction history, identifies unusual patterns, "
        "deviations from expected activity, and evaluates triggered AML transaction monitoring alerts."
    ),
    model=_model(),
    before_model_callback=before_model_context,
    after_model_callback=after_model_usage,
    instruction=f"""You are the Transaction Agent in a financial crime investigation.

   Your job: analyse the customer's transactions, run rule-based Transaction Monitoring (TM),
   and surface AML typologies.

   Steps:
   1. Call `get_transaction_evidence` with focus="aml" for full-population totals and a bounded page of exact records.
   2. Call `analyze_transactions` to get computed metrics, anomaly flags, and triggered TM rules.
   3. Call `get_transaction_alerts` to retrieve itemized AML alerts with supporting transaction IDs.
   4. Call `get_expected_activity` to compare actual vs expected behaviour.
   5. If omitted records leave material gaps, retrieve additional pages using next_offset,
      or call `get_transactions` for the full history. A selected page is not evidence that omitted records are clean.

   Report back, concisely:
   - Transaction patterns (total volume, count, channels, direction, velocity)
   - Itemized AML alerts triggered (e.g. TM-01 Structuring, TM-02 Money Mule pass-through,
     TM-03 Turnover deviation, TM-04 Single spike, TM-05 Corridors, TM-06 Dormancy, TM-07 Round amounts)
     including alert severity and score impact
   - Deviations from the expected activity profile (volume ratio, transaction velocity)
   - Specific transactions, amounts, and dates that serve as the strongest AML evidence

   {_SYNTHETIC_ONLY}
   """,
    tools=TRANSACTION_TOOLS,
    output_key="transaction_findings",
)


fraud_agent = Agent(
    name="fraud_agent",
    description=(
        "Analyses digital identity telemetry, device fingerprints, impossible travel velocity, "
        "and first-party and third-party fraud typologies (ATO, card micro-testing, APP scams, bust-out)."
    ),
    model=_model(),
    before_model_callback=before_model_context,
    after_model_callback=after_model_usage,
    instruction=f"""You are the Fraud & Cybercrime Agent in a financial crime investigation.

   Your job: investigate cybercrime, digital identity anomalies, device telemetry,
   and first-party / third-party fraud typologies.

   Steps:
   1. Call `get_fraud_alerts` for the customer to inspect triggered fraud alerts.
   2. Call `get_digital_telemetry` to audit device IDs, IP addresses, authentication status, and contact line types.
   3. Call `get_transaction_evidence` with focus="fraud" to examine exact payment records and full-population totals.
      Retrieve additional pages using next_offset or call `get_transactions` when omitted records leave material gaps.
      A selected page is not evidence that omitted records are clean.

   Report back, concisely:
   - Itemized Fraud Alerts (e.g. FR-01 Account Takeover / Impossible Travel, FR-02 Card Micro-Testing,
     FR-03 Authorized Push Payment Scams, FR-04 Bust-Out / Deposit Kiting, FR-05 Synthetic Identity Fraud)
   - Device & Session Telemetry: Recognized vs anomalous devices, foreign IP sessions, impossible travel (>900 km/h)
   - Payment Forensics: Card entry modes (EMV vs CNP eCommerce), authorization declines (DECLINED_SUSPECTED_FRAUD),
     new payee velocity
   - Digital Identity Veracity: Disposable burner email domains, VoIP PBX lines, SSN/DOB dissonance
   - Fraud Risk Verdict: Is the account an compromised victim (ATO/Scam) or a malicious actor (Bust-out/Synthetic ID)?

   {_SYNTHETIC_ONLY}
   """,
    tools=FRAUD_TOOLS,
    output_key="fraud_findings",
)


ownership_agent = Agent(
    name="ownership_agent",
    description=(
        "Analyses company ownership and control structures, including "
        "jurisdictions, beneficial owners (UBOs), and country AML risks."
    ),
    model=_model(),
    before_model_callback=before_model_context,
    after_model_callback=after_model_usage,
    instruction=f"""You are the Ownership Agent in a financial crime investigation.

   Your job: map who owns and controls the customer entity or evaluate corporate/employment links.

   Steps:
   1. Call `get_ownership_structure` for the customer.
   2. For each jurisdiction that appears, call `get_country_risk` to rate it.

   Report back, concisely:
   - Shareholders and their equity stakes (identifying the Ultimate Beneficial Owner / UBO)
   - Directors and executive control roles
   - Jurisdictions involved and their risk ratings (FATF Blacklist/Greylist, Offshore Secrecy, OECD)
   - Any layered, opaque, or nominee-like structures
   - Any politically exposed persons in the control chain

   {_SYNTHETIC_ONLY}
   """,
    tools=OWNERSHIP_TOOLS,
    output_key="ownership_findings",
)


risk_agent = Agent(
    name="risk_agent",
    description=(
        "Evaluates the multi-pillar FRAML risk assessment, explains composite scores, "
        "sub-scores (AML vs Fraud), statutory/fraud overrides, and operational audit checklists."
    ),
    model=_model(),
    before_model_callback=before_model_context,
    after_model_callback=after_model_usage,
    instruction=f"""You are the Risk Agent in a financial crime investigation.

   Your job: evaluate the multi-pillar FRAML risk score generated by the Risk Engine,
   explain why each risk indicator matters, and recommend operational compliance actions.

   Steps:
   1. Call `get_risk_assessment` for the customer's 5-pillar risk assessment breakdown.
   2. Call `get_customer_profile` and `get_country_risk` for additional risk context if needed.

   Report back, concisely:
   - Composite FRAML Score: Overall score (0-100) and assigned Risk Tier (LOW, MEDIUM, HIGH, CRITICAL)
   - Sub-Score Breakdown:
     * AML Sub-Score (0-100)
     * Fraud Sub-Score (0-100)
   - 5-Pillar Breakdown:
     * Pillar 1: Customer KYC & Demographics (20%)
     * Pillar 2: Purpose & Nature of Relationship (10%)
     * Pillar 3: Products & Onboarding Channels (10%)
     * Pillar 4: AML Transaction Monitoring (30%)
     * Pillar 5: Fraud Risk & Digital Footprint (30%)
   - Regulatory & Fraud Overrides applied (e.g. Sanctions hit, FATF Blacklist corridor, ATO confirmation,
     Bust-out kiting, 31 U.S.C. 5324 Structuring, Foreign PEP EDD)
   - Recommended operational action (e.g. FILE_SAR_AND_RESTRICT_ACCOUNT, FREEZE_CARD_CREDENTIALS, ENHANCED_DUE_DILIGENCE)
   - Concrete Compliance Audit Checklist steps to be executed by the operational team

   {_SYNTHETIC_ONLY}
   """,
    tools=RISK_TOOLS,
    output_key="risk_findings",
)


# --------------------------------------------------------------------------
# Investigation Agent (orchestrator / root)
# --------------------------------------------------------------------------
# The five specialists run in a deterministic sequence so every case gets
# comprehensive FRAML coverage across KYC, Transactions, Fraud, Ownership, and Risk.
# Each writes its findings to session state via `output_key`.
# The consolidator then reads all five and produces the final investigation.

_sub_agents = [
    customer_agent,
    transaction_agent,
    fraud_agent,
    ownership_agent,
    risk_agent,
]
if arbiter_agent is not None:
    arbiter_agent.before_model_callback = before_model_context
    arbiter_agent.after_model_callback = after_model_usage
    _sub_agents.append(arbiter_agent)

investigation_pipeline = SequentialAgent(
    name="investigation_pipeline",
    description=(
        "Runs the specialist agents in sequence, followed by the senior Arbiter Tribunal Agent "
        "to resolve cross-specialist contradictions."
    ),
    sub_agents=_sub_agents,
)


consolidator_agent = Agent(
    name="consolidator_agent",
    description=(
        "Consolidates the specialist findings and Arbiter Tribunal rulings into the final "
        "investigation report for a human investigator, starting with an executive case overview."
    ),
    model=_model(),
    before_model_callback=before_model_context,
    after_model_callback=after_model_usage,
    instruction=f"""You are the Consolidator Agent. The specialist agents and Arbiter Tribunal
   have completed their work; their findings and debate rulings are in your context.

   Consolidate them into ONE final investigation report with exactly these
   sections:

   - Case overview
   - Customer overview
   - Key observations
   - Transaction patterns & AML monitoring
   - Fraud & cybercrime telemetry findings
   - Ownership & control findings
   - Relevant risk indicators & FRAML score
   - Evidence supporting each finding
   - Contradictory or mitigating evidence
   - Multi-specialist cross-debate & contradiction resolution (Arbiter Tribunal ruling)
   - Missing information
   - Suggested next investigative questions
   - Overall case summary

   Section Guidelines:
   - Case overview: Executive case summary at the top:
     * Case Identifier / Reference (e.g. Case CUST-00015)
     * Subject Under Review (Customer Name, ID, Entity Type, Jurisdiction)
     * Dynamic Triage Classification & Topology
     * Investigation Trigger / Rationale (Specific alert IDs: e.g. TM-01 Structuring, FR-01 ATO, or High-Risk Influx)
     * Investigation Scope & Timeline (Transaction window, count, and dollar volume)
     * Primary Typologies Identified (Core AML or Fraud typologies suspected)
     * Case Classification & Priority (e.g. CRITICAL / Immediate Escalation)
     * Executive Synopsis (2-3 sentences summarizing the situation)
   - Customer overview: Background, CDD findings, wealth-to-income plausibility, and watchlists.
   - Key observations: High-impact cross-specialist findings.
   - Transaction patterns & AML monitoring: Inflows, outflows, channel concentrations, and triggered TM rule alerts.
   - Fraud & cybercrime telemetry findings: Device anomalies, impossible travel, card entry modes, decline attempts, burner credentials.
   - Ownership & control findings: UBOs, directorships, employer links, and offshore secrecy jurisdictions.
   - Relevant risk indicators & FRAML score: Composite score (0-100), risk tier, 5-pillar breakdown, and overrides.
   - Evidence supporting each finding: Specific transaction dates, IDs, devices, IPs, channels, and records cited.
   - Contradictory or mitigating evidence: Clean history factors, legitimate explanations, or lack of derogatory hits.
   - Multi-specialist cross-debate & contradiction resolution: Report the Arbiter Agent's
     cross-examination findings, whether Money Mule vs APP Coercion or ATO vs Friendly Fraud
     tension was detected, the calibrated confidence score, and the Tribunal's final consensus verdict.
   - Missing information: Data gaps, pending source-of-wealth documentation, or unverified counterparties.
   - Suggested next investigative questions: Concrete audit checklist steps for the compliance team.
   - Overall case summary: Final concluding recommendation (e.g. SAR filing, account freeze, EDD review),
     synthetic data disclaimer, and explicit statement that human compliance officers make all legal decisions.

   Rules:
   - Cite the specific numbers, dates, transaction IDs, and alert IDs reported by specialists.
   - Where specialists disagree or evidence is inconclusive, note it explicitly.
   - Do not invent facts that no specialist reported.

   {_SYNTHETIC_ONLY}
   You present evidence and analysis for a HUMAN investigator to review. You do
   NOT make an autonomous legal or regulatory decision, and you must state that
   plainly in the case summary.
   """,
)


root_agent = SequentialAgent(
    name="investigation_agent",
    description=(
        "Coordinates a comprehensive FRAML financial crime investigation: "
        "runs the specialist agents in sequence, then consolidates their findings."
    ),
    sub_agents=[investigation_pipeline, consolidator_agent],
)

app = App(
    root_agent=root_agent,
    name="app",
)
