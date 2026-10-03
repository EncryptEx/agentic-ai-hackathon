"""Unit tests for the Customer Verification & Call Agent (Anti-Tipping-Off Safeguards & Video Persona)."""

import pytest
from app.customer_call_agent import (
    CustomerCallSession,
    PROHIBITED_TIPPING_OFF_TERMS,
    start_customer_call,
    process_call_turn,
    complete_customer_call,
)


def test_anti_tipping_off_prohibited_terms_defined():
    """Verify that statutory financial crime terms are protected by anti-tipping-off safeguards."""
    assert "sar" in PROHIBITED_TIPPING_OFF_TERMS
    assert "money laundering" in PROHIBITED_TIPPING_OFF_TERMS
    assert "structuring" in PROHIBITED_TIPPING_OFF_TERMS
    assert "money mule" in PROHIBITED_TIPPING_OFF_TERMS
    assert "tip off" in PROHIBITED_TIPPING_OFF_TERMS


def test_anti_tipping_off_scrubber():
    """Verify that any accidental leak of prohibited terms is scrubbed automatically."""
    session = CustomerCallSession("CUST-00015")
    leaked_text = "We noticed structuring and a potential SAR was filed for money laundering."
    sanitized = session._sanitize_tipping_off(leaked_text)
    
    assert "structuring" not in sanitized.lower()
    assert "sar" not in sanitized.lower()
    assert "money laundering" not in sanitized.lower()
    assert "routine banking verification" in sanitized


def test_call_session_initialization():
    """Verify that a customer call session initializes goals based on customer archetype."""
    session_structuring = CustomerCallSession("CUST-00015")
    assert session_structuring.customer_id == "CUST-00015"
    assert session_structuring.customer_name == "James Moran"
    assert len(session_structuring.inquiry_goals) > 0
    # For James Moran (structuring), inquiry goals must mention cash deposits/origin
    assert any("cash" in g.lower() for g in session_structuring.inquiry_goals)

    # For Kimberly Henson (money mule / wire)
    session_mule = CustomerCallSession("CUST-00019")
    assert any("wire" in g.lower() or "sender" in g.lower() for g in session_mule.inquiry_goals)


def test_viseme_estimator():
    """Verify viseme timing generator produces sequential time-based viseme cues for lip sync."""
    session = CustomerCallSession("CUST-00015")
    cues = session._estimate_visemes("Hello James, this is Agent Claire Sterling.")
    assert len(cues) > 0
    assert "viseme" in cues[0]
    assert "time" in cues[0]
    assert "duration" in cues[0]
    # Times must be non-decreasing
    for i in range(len(cues) - 1):
        assert cues[i]["time"] <= cues[i + 1]["time"]


def test_opening_greeting_polite_and_non_tipping_off():
    """Verify the opening verbal greeting does not accuse the customer."""
    res = start_customer_call("CUST-00015")
    assert res["session_id"].startswith("CALL-")
    assert "James" in res["message"]
    assert "Claire Sterling" in res["message"]
    # Verify no illegal tipping-off in greeting
    for term in ["sar", "structuring", "aml", "fraud alert", "money laundering"]:
        assert term not in res["message"].lower()
