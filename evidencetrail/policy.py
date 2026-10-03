"""Deterministic policy v1 (illustrative demo rule, not validated banking policy).

Signals are derived from recorded evidence payloads only, never from agent claims.
The policy controls the simulated action. The agent's recommendation is recorded and a more cautious
one is flagged as a disagreement (it only raises the action if escalation is explicitly enabled). A single
Jev probability can neither authorize nor block a transfer.
"""

from .config import POLICY_VERSION, agent_may_escalate

SEVERITY = {"ALLOW": 0, "CONTEXT_CHECK": 1, "REVIEW": 2}
CONTEXT_QUESTION = ("Has someone asked you to move this money to a 'safe account', "
                    "keep the transfer secret, or act urgently?")

_REQUIRED = {"behavior_profile": "get_behavior_profile",
             "device_inspection": "inspect_device",
             "recipient_inspection": "inspect_recipient"}


def _latest(store, type_):
    items = store.by_type(type_)
    return items[-1] if items else None


def derive_signals(store, transaction):
    """Return supported signals plus the evidence ids that support each."""
    sig = {"device_compromise": None, "unusual_amount": None, "new_recipient": None,
           "recipient_suspicious": None, "network_suspicious": None}
    behavior = _latest(store, "behavior_profile")
    device = _latest(store, "device_inspection")
    recipient = _latest(store, "recipient_inspection")
    graph = _latest(store, "relationship_graph")

    if device:
        p = device["payload"]
        meaningful = [a for a in p.get("session_anomalies", []) if a.get("severity") == "meaningful"]
        if not p.get("device_known", True) and meaningful:
            sig["device_compromise"] = {"evidence_ids": [device["evidence_id"]],
                                        "detail": f"new device with {meaningful[0]['type']}"}
    if behavior:
        p = behavior["payload"]
        amt = transaction["amount"]
        if amt > p["typical_amount_max"] or amt < p["typical_amount_min"]:
            sig["unusual_amount"] = {"evidence_ids": [behavior["evidence_id"]],
                                     "detail": f"{amt} outside {p['typical_amount_min']}-{p['typical_amount_max']}"}
        if transaction["recipient_id"] not in p.get("known_recipient_ids", []):
            sig["new_recipient"] = {"evidence_ids": [behavior["evidence_id"]],
                                    "detail": "recipient not in known recipients"}
    if recipient:
        p = recipient["payload"]
        reasons = []
        age = p.get("account_age_days")  # None = unknown, which is not evidence that the account is young
        if age is not None and age <= 7 and p["incoming_transfers_last_90_min"] >= 10:
            reasons.append(f"{age}-day-old account with "
                           f"{p['incoming_transfers_last_90_min']} incoming transfers in 90 min")
        if p["prior_synthetic_flags"] > 0:
            reasons.append("prior synthetic flags")
        if reasons:
            sig["recipient_suspicious"] = {"evidence_ids": [recipient["evidence_id"]],
                                           "detail": "; ".join(reasons)}
    if graph and graph["payload"].get("synthetically_flagged_node_ids"):
        flagged = graph["payload"]["synthetically_flagged_node_ids"]
        sig["network_suspicious"] = {"evidence_ids": [graph["evidence_id"]],
                                     "detail": f"linked to synthetically flagged account(s) {flagged}"}
    return sig


def missing_checks(store, signals):
    """Required relevant checks that have no successful evidence."""
    missing = [tool for ev_type, tool in _REQUIRED.items() if not store.by_type(ev_type)]
    if signals["new_recipient"] and not store.by_type("relationship_graph"):
        missing.append("search_relationship_graph")
    return missing


def validate_claims(store, claims):
    """Check cited IDs exist in the run. Does NOT establish semantic support."""
    out, cited, valid = [], 0, 0
    for i, c in enumerate(claims, 1):
        ids = c.get("supporting_evidence_ids", [])
        bad = [e for e in ids if not store.has(e)]
        cited += len(ids)
        valid += len(ids) - len(bad)
        out.append({"claim_id": f"CL-{i:02d}", "text": c.get("text", ""),
                    "supporting_evidence_ids": ids, "invalid_evidence_ids": bad,
                    "semantic_support": "ungraded"})
    return out, cited, valid


def incomplete(reason, signals=None, claims=None, agent=None):
    return {"policy_version": POLICY_VERSION, "status": "INCOMPLETE", "simulated_action": "REVIEW",
            "rule": "incomplete_evidence", "reason_code": "INCOMPLETE_REVIEW", "explanation": reason,
            "signals": signals or {}, "claims": claims or [], "agent_recommendation": agent,
            "context_check": None, "reference_validity": None}


def decide(store, transaction, finish):
    signals = derive_signals(store, transaction)
    claims, cited, valid = validate_claims(store, finish.get("claims", []))
    agent = {"recommended_action": finish.get("recommended_action"), "status": finish.get("status"),
             "remaining_uncertainty": finish.get("remaining_uncertainty"),
             "reason_code": finish.get("reason_code")}
    validity = {"cited": cited, "valid": valid}
    present = {k: v for k, v in signals.items() if v}

    def result(action, status, rule, reason, explanation):
        escalated, disagreement = False, None
        if status == "COMPLETE" and SEVERITY.get(agent["recommended_action"], 0) > SEVERITY[action]:
            if agent_may_escalate():
                explanation += " Agent recommendation was more cautious than policy and was kept."
                action, escalated = agent["recommended_action"], True
            else:
                disagreement = "agent_more_cautious"  # shown to the user from this flag, not from the explanation text
        elif status == "COMPLETE" and SEVERITY.get(agent["recommended_action"], 0) < SEVERITY[action]:
            disagreement = "agent_less_cautious"
        return {"policy_version": POLICY_VERSION, "status": status, "simulated_action": action,
                "rule": rule, "reason_code": reason, "explanation": explanation, "signals": present,
                "claims": claims, "agent_recommendation": agent, "agent_escalation": escalated, "agent_disagreement": disagreement,
                "context_check": ({"question": CONTEXT_QUESTION, "answer": None}
                                  if action == "CONTEXT_CHECK" else None),
                "reference_validity": validity}

    if signals["device_compromise"]:
        return result("REVIEW", "COMPLETE", "device_compromise", "DEVICE_COMPROMISE_SIGNAL",
                      "Device-compromise signals supported by recorded evidence.")
    problems = []
    if any(c["invalid_evidence_ids"] for c in claims):
        problems.append("claims cite evidence IDs that do not exist in this run")
    if not claims:
        problems.append("no evidence-backed claims were submitted")
    gaps = missing_checks(store, signals)
    if gaps:
        problems.append("missing evidence from: " + ", ".join(gaps))
    if agent["status"] == "INCOMPLETE":
        problems.append("agent reported the investigation as incomplete")
    if problems:
        r = result("REVIEW", "INCOMPLETE", "incomplete_evidence", "INCOMPLETE_REVIEW",
                   "; ".join(problems) + ". Missing evidence is not reassuring evidence.")
        r["simulated_action"] = "REVIEW"
        return r
    if (signals["unusual_amount"] and signals["new_recipient"]
            and (signals["recipient_suspicious"] or signals["network_suspicious"])):
        return result("CONTEXT_CHECK", "COMPLETE", "unusual_new_suspicious", "MANIPULATION_INDICATORS",
                      "Unusual transfer to a new recipient with suspicious recipient/network evidence.")
    if signals["recipient_suspicious"] or signals["network_suspicious"]:
        return result("CONTEXT_CHECK", "COMPLETE", "partial_elevated_signals", "PARTIAL_ELEVATED_SIGNALS",
                      "Supported recipient/network risk indicators do not meet a stronger rule.")
    return result("ALLOW", "COMPLETE", "no_elevated_signals", "NO_ELEVATED_SIGNALS",
                  "Relevant checks completed with no supported elevated signals.")


def apply_context_answer(final, answer):
    """Simulated customer answer to the context check. 'yes' -> REVIEW; 'no' clears nothing."""
    if final.get("simulated_action") != "CONTEXT_CHECK" or not final.get("context_check"):
        raise ValueError("no context check is pending for this run")
    if answer not in ("yes", "no"):
        raise ValueError("answer must be 'yes' or 'no'")
    final["context_check"]["answer"] = answer
    final.setdefault("action_before_context_answer", final["simulated_action"])
    if answer == "yes":
        final["simulated_action"] = "REVIEW"
        final["reason_code"] = "COERCION_REPORTED"
        final["explanation"] += " Customer reported coercion indicators; routed to review."
    else:
        final["explanation"] += (" Customer answered 'no'; this does not clear the other supported "
                                 "signals, so the context check remains the outcome.")
    return final
