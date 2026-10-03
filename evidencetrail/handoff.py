"""Hand an EvidenceTrail alert to the ADK specialist team for a customer-level investigation.

EvidenceTrail decides at the level of one transfer; the ADK team (app/agent.py) investigates the
customer across KYC, transactions, fraud telemetry, ownership and FRAML risk. The hand-off only
attaches the team's report to the alert. It never changes the simulated action.

ADK and the host database are imported lazily so EvidenceTrail still runs without them.
"""

import asyncio

from .canon import now_utc

SOURCE_AGENTS = "adk_agents"
SOURCE_FALLBACK = "specialist_tools_fallback"


class CustomerNotFound(Exception):
    """The customer is not in the FRAML host database the ADK tools read from."""


def trigger_alert(alert):
    """Map an EvidenceTrail alert onto the trigger-alert shape the ADK prompt builder expects."""
    tx = alert["transaction"]
    summary = (f"EvidenceTrail transfer alert {alert['alert_id']}: {alert['title']}. {alert['summary']} "
               f"Transfer {tx['transaction_id']} of {tx['amount']} {tx['currency']} to recipient "
               f"{tx['recipient_id']}. Policy outcome: {alert['policy']['action']} "
               f"({alert['policy']['status']}).")
    return {"rule_id": "EVIDENCETRAIL", "rule_name": alert["title"],
            "severity": alert["severity"].upper(), "summary": summary[:900]}


def prepare(alert, customer_id=None):
    """Resolve the FRAML customer and build the dispatch prompt. Raises CustomerNotFound."""
    from app.alert_feed import AlertDispatcher
    cust = (customer_id or alert["transaction"]["customer_id"]).upper().strip()
    dispatcher = AlertDispatcher()
    try:
        packet = dispatcher.prepare_case_packet(cust)
    except ValueError as e:
        raise CustomerNotFound(str(e)) from None
    prompt = dispatcher.generate_investigation_prompt(cust, trigger_alert(alert))
    return cust, packet, prompt


async def run_adk(runner, app_name, prompt):
    """Run the ADK pipeline. Returns (report_text, error_class_name_or_None)."""
    from google.genai import types
    if not runner or not getattr(runner, "session_service", None):
        return "", "NoRunner"
    report = ""
    try:
        session = await runner.session_service.create_session(app_name=app_name, user_id="evidencetrail_handoff")
        message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        async for event in runner.run_async(user_id="evidencetrail_handoff", session_id=session.id,
                                            new_message=message):
            content = getattr(event, "content", None)
            for part in (getattr(content, "parts", None) or []):
                if getattr(part, "text", None):
                    report = part.text
    except Exception as e:  # credentials missing, quota, network... never leak the message
        return "", type(e).__name__
    return report, None


async def execute(alert, customer_id, packet, prompt, runner, app_name):
    """Produce the hand-off record. Labels honestly which path produced the report."""
    report, adk_error = await run_adk(runner, app_name, prompt)
    source = SOURCE_AGENTS
    if not report.strip():
        from app.alert_feed import generate_specialist_investigation_report
        report = await asyncio.to_thread(generate_specialist_investigation_report, customer_id,
                                         trigger_alert(alert))
        source = SOURCE_FALLBACK
    return {"status": "completed", "customer_id": customer_id, "customer_name": packet.get("customer_name"),
            "archetype": packet.get("archetype"), "risk_tier": packet.get("risk_tier"),
            "composite_score": packet.get("composite_score"), "report_source": source,
            "adk_error": adk_error, "prompt_dispatched": prompt, "report": report,
            "completed_at": now_utc(),
            "note": ("Report written by the ADK specialist agents." if source == SOURCE_AGENTS else
                     "The ADK agents could not run, so this report was synthesized directly from the specialist "
                     "data tools without an LLM.") + " It does not change the EvidenceTrail simulated action."}
