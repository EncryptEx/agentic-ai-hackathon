"""Google ADK Arbiter Agent and Dynamic Orchestration Agent."""

from typing import Dict, Any, Optional
import os

try:
    from google.adk.agents import Agent
    from google.adk.models import Gemini
    from google.genai import types
    HAS_ADK = True
except ImportError:
    HAS_ADK = False

from app.orchestrator.triage import DynamicTriageRouter
from app.orchestrator.debate import DialecticDebateEngine, DebateOutcome

MODEL = "gemini-3.8-flash"

ARBITER_INSTRUCTION = """You are the Senior Financial Crime Tribunal Arbiter Agent.

Your solemn responsibility is to review the independent findings of specialist agents
(Customer KYC, Transaction AML, Fraud Telemetry, Corporate Ownership, and Risk Scoring)
and identify any CONTRADICTORY or DIVERGENT hypotheses.

Primary Responsibilities:
1. Detect logical or evidential tensions:
   - Money Mule vs. APP Coercion Victim (Is the customer intentionally laundering or under active scam coercion?)
   - Account Takeover (ATO) vs. Friendly Fraud / Authorized VPN Session
   - High-Volume Wealth Influx vs. Layered Structuring
2. Challenge conflicting specialists:
   - Pose rigorous cross-examination queries targeting specific transaction timestamps, device IDs, and authorization flags.
3. Deliver a definitive, calibrated Tribunal Consensus:
   - State the winning hypothesis, the confidence score (0-100%), and the recommended statutory outcome.
   - Clarify whether punitive restrictions or protective victim-interception protocols should be enacted.

All data is SYNTHETIC and fictional. You provide calibrated forensic analysis for human compliance officers.
"""


def build_arbiter_agent():
    """Build the Google ADK Arbiter Agent if ADK is installed."""
    if not HAS_ADK:
        return None

    return Agent(
        name="arbiter_agent",
        description=(
            "Adjudicates contradictions, resolves hypothesis conflicts between specialists, "
            "and delivers an evidence-weighted Tribunal consensus."
        ),
        model=Gemini(
            model=MODEL,
            retry_options=types.HttpRetryOptions(attempts=3),
        ),
        instruction=ARBITER_INSTRUCTION,
        output_key="tribunal_findings",
    )


arbiter_agent = build_arbiter_agent()
