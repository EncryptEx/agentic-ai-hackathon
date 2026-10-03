"""Deterministic Policy Engine for EvidenceTrail.
Constrains agent recommendations and enforces banking compliance rules.
"""

from typing import Dict, Any, List, Optional

class PolicyEngine:
    """Enforces deterministic rule-based compliance gates over AI recommendations."""
    
    @staticmethod
    def evaluate(agent_recommendation: str, evidence_list: List[Dict[str, Any]], cited_evidence_ids: List[str]) -> Dict[str, Any]:
        """Validates referenced evidence and determines the binding policy intervention."""
        evidence_by_id = {e["evidence_id"]: e for e in evidence_list}
        
        # 1. Validate citation presence
        invalid_ids = [eid for eid in cited_evidence_ids if eid not in evidence_by_id]
        if invalid_ids:
            return {
                "action": "REVIEW",
                "status": "INCOMPLETE",
                "policy_rule": "INVALID_EVIDENCE_CITATION",
                "reason": f"Agent cited non-existent evidence IDs: {', '.join(invalid_ids)}",
                "requires_context_check": False
            }

        # 2. Check for customer inquiry statement (from Question Bank response)
        inquiry_evidence = [e for e in evidence_list if e["type"] == "customer_inquiry_statement"]
        if inquiry_evidence:
            latest_inquiry = inquiry_evidence[-1]
            verdict = latest_inquiry["payload"].get("risk_verdict")
            statement = latest_inquiry["payload"].get("customer_statement")
            if verdict in ("CONFIRMED_COERCION", "CONFIRMED_ATO", "INVESTMENT_TRAP", "SUSPECTED_INVOICE_INTERCEPTION"):
                return {
                    "action": "REVIEW",
                    "status": "COMPLETE",
                    "policy_rule": "RULE_COERCION_CONFIRMED_INTERCEPT",
                    "reason": f"Customer statement confirmed active fraud coercion ({verdict}): {statement}. Funds frozen in escrow.",
                    "supporting_evidence_ids": [latest_inquiry["evidence_id"]],
                    "requires_context_check": False
                }
            elif verdict in ("VOLUNTARY_UNCOERCED", "AUTHORIZED_LEGITIMATE", "VERIFIED_SUPPLIER"):
                # Check if counterparty still carries critical network/mule risk
                rec_risk = any(e["type"] == "network_graph" and len(e["payload"].get("flagged_nodes", [])) > 0 for e in evidence_list)
                if rec_risk:
                    return {
                        "action": "REVIEW",
                        "status": "COMPLETE",
                        "policy_rule": "RULE_VOLUNTARY_BUT_MULE_RISK",
                        "reason": "Customer affirmed voluntary intent, but recipient remains linked to active mule accounts. Mandatory fraud analyst consultation required.",
                        "supporting_evidence_ids": [latest_inquiry["evidence_id"]],
                        "requires_context_check": False
                    }
                else:
                    return {
                        "action": "ALLOW",
                        "status": "COMPLETE",
                        "policy_rule": "RULE_VOLUNTARY_CUSTOMER_CONFIRMED",
                        "reason": "Customer explicitly confirmed payment purpose without social engineering indicators.",
                        "supporting_evidence_ids": [latest_inquiry["evidence_id"]],
                        "requires_context_check": False
                    }

        # 3. Check for device-compromise signals
        device_compromise = False
        device_evidence_id = None
        for eid in cited_evidence_ids:
            e = evidence_by_id[eid]
            if e["type"] == "device_telemetry" and e["payload"].get("has_anomalies"):
                device_compromise = True
                device_evidence_id = eid

        if device_compromise:
            return {
                "action": "REVIEW",
                "status": "COMPLETE",
                "policy_rule": "RULE_DEVICE_COMPROMISE_DETECTED",
                "reason": "Critical session anomalies and impossible travel detected on originating device.",
                "supporting_evidence_ids": [device_evidence_id],
                "requires_context_check": False
            }

        # 4. Check for Manipulated Payer (APP scam) pattern:
        # Unusual amount + new recipient + suspicious recipient or network graph link
        behavior_unusual = False
        recipient_suspicious = False
        network_suspicious = False
        manipulated_evidence_ids = []

        for eid in cited_evidence_ids:
            e = evidence_by_id[eid]
            if e["type"] == "customer_behavior" and e["payload"].get("is_outside_typical_range") and not e["payload"].get("is_known_recipient"):
                behavior_unusual = True
                manipulated_evidence_ids.append(eid)
            if e["type"] == "recipient_record" and (e["payload"].get("is_high_velocity_mule") or len(e["payload"].get("synthetic_flags", [])) > 0):
                recipient_suspicious = True
                manipulated_evidence_ids.append(eid)
            if e["type"] == "network_graph" and len(e["payload"].get("flagged_nodes", [])) > 0:
                network_suspicious = True
                manipulated_evidence_ids.append(eid)

        if behavior_unusual and (recipient_suspicious or network_suspicious):
            return {
                "action": "CONTEXT_CHECK",
                "status": "COMPLETE",
                "policy_rule": "RULE_MANIPULATED_PAYER_INTERVENTION",
                "reason": "Unusual transfer volume to unestablished recipient linked to high-velocity mule cluster.",
                "supporting_evidence_ids": manipulated_evidence_ids,
                "requires_context_check": True,
                "context_check_prompt": (
                    "Has someone asked you to move this money to a 'safe account', "
                    "keep the transfer secret, or act urgently?"
                )
            }

        # 4. Routine / cleared checks with no elevated signals
        has_behavior = any(evidence_by_id[eid]["type"] == "customer_behavior" for eid in cited_evidence_ids)
        has_device = any(evidence_by_id[eid]["type"] == "device_telemetry" for eid in cited_evidence_ids)
        
        if has_behavior and has_device and not device_compromise and not recipient_suspicious and not network_suspicious:
            return {
                "action": "ALLOW",
                "status": "COMPLETE",
                "policy_rule": "RULE_ROUTINE_VERIFIED_CLEAR",
                "reason": "Transfer conforms to historical customer baseline, verified trusted device, and zero risk indicators.",
                "supporting_evidence_ids": cited_evidence_ids,
                "requires_context_check": False
            }

        # Default fallback: honor agent recommendation if supported or route to REVIEW
        return {
            "action": agent_recommendation if agent_recommendation in ("ALLOW", "CONTEXT_CHECK", "REVIEW") else "REVIEW",
            "status": "COMPLETE",
            "policy_rule": "RULE_STANDARD_TRIAGE",
            "reason": "Standard triage baseline applied.",
            "supporting_evidence_ids": cited_evidence_ids,
            "requires_context_check": agent_recommendation == "CONTEXT_CHECK"
        }

    @staticmethod
    def apply_context_check_response(current_decision: Dict[str, Any], user_response: str) -> Dict[str, Any]:
        """Applies customer response to the simulated social-engineering intervention prompt."""
        if user_response.lower() in ("yes", "true", "coerced"):
            return {
                **current_decision,
                "action": "REVIEW",
                "status": "COMPLETE",
                "policy_rule": "RULE_COERCION_CONFIRMED_INTERCEPT",
                "reason": "Customer confirmed social engineering indicators ('safe account' or urgent instruction). Payment routed to fraud prevention specialist.",
                "requires_context_check": False,
                "customer_response": "Yes (Coercion confirmed)"
            }
        else:
            return {
                **current_decision,
                "action": "ALLOW",
                "status": "COMPLETE",
                "policy_rule": "RULE_VOLUNTARY_CUSTOMER_CONFIRMED",
                "reason": "Customer explicitly confirmed payment purpose without social engineering indicators.",
                "requires_context_check": False,
                "customer_response": "No (Voluntary transfer)"
            }
