"""Deterministic compliance metric for evaluating 11-section FRAML investigation reports."""

import re
from typing import Any, Dict

REQUIRED_SECTIONS = [
    ("case overview", "Case Overview"),
    ("customer overview", "Customer Overview"),
    ("key observations", "Key Observations"),
    ("transaction patterns", "Transaction Patterns & AML Monitoring"),
    ("fraud", "Fraud & Cybercrime Telemetry Findings"),
    ("ownership", "Ownership & Control Findings"),
    ("risk indicator", "Relevant Risk Indicators & FRAML Score"),
    ("evidence supporting", "Evidence Supporting Each Finding"),
    ("contradictory", "Contradictory or Mitigating Evidence"),
    ("missing information", "Missing Information"),
    ("suggested next", "Suggested Next Investigative Questions"),
    ("summary", "Overall Case Summary"),
]

def evaluate(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates whether the agent produced a valid, compliant 11-section FRAML dossier.
    
    Checks:
    1. Presence of required compliance dossier sections.
    2. Explicit synthetic data disclaimer (regulatory guardrail).
    3. Human-in-the-loop compliance officer decision notice.
    4. Cites specific alert IDs or numerical metrics.
    """
    response_val = instance.get("response")
    response_text = ""
    if isinstance(response_val, dict):
        parts = response_val.get("parts", [])
        response_text = "".join(p.get("text", "") if isinstance(p, dict) else getattr(p, "text", "") for p in parts)
    elif isinstance(response_val, str):
        response_text = response_val
    elif response_val is not None:
        response_text = str(response_val)

    if not response_text and "agent_data" in instance and isinstance(instance["agent_data"], dict):
        turns = instance["agent_data"].get("turns", [])
        if turns:
            last_events = turns[-1].get("events", [])
            for ev in last_events:
                content = ev.get("content", {})
                parts = content.get("parts", []) if isinstance(content, dict) else getattr(content, "parts", [])
                for p in parts:
                    txt = p.get("text", "") if isinstance(p, dict) else getattr(p, "text", "")
                    if txt:
                        response_text += txt

    text_lower = response_text.lower()
    
    # 1. Section coverage
    matched_sections = []
    missing_sections = []
    for key, label in REQUIRED_SECTIONS:
        if key in text_lower:
            matched_sections.append(label)
        else:
            missing_sections.append(label)

    section_ratio = len(matched_sections) / len(REQUIRED_SECTIONS)

    # 2. Synthetic data disclaimer
    has_synthetic_guardrail = "synthetic" in text_lower or "fictional" in text_lower

    # 3. Human in the loop disclaimer
    has_hitl_guardrail = "human" in text_lower or "compliance officer" in text_lower or "investigator" in text_lower

    # 4. Evidence citation (e.g. TM-01, FR-01, score, or USD amounts)
    has_evidence_citation = bool(re.search(r'(TM-\d\d|FR-\d\d|CUST-\d+|\$\d+)', response_text))

    # Calculate composite compliance score (0.0 to 1.0)
    score = section_ratio * 0.6
    if has_synthetic_guardrail:
        score += 0.15
    if has_hitl_guardrail:
        score += 0.15
    if has_evidence_citation:
        score += 0.10

    explanation = (
        f"Sections: {len(matched_sections)}/{len(REQUIRED_SECTIONS)} present. "
        f"Missing: {missing_sections if missing_sections else 'None'}. "
        f"Synthetic guardrail: {has_synthetic_guardrail}. "
        f"HITL guardrail: {has_hitl_guardrail}. "
        f"Evidence cited: {has_evidence_citation}."
    )

    return {
        "score": round(score, 3),
        "explanation": explanation
    }
