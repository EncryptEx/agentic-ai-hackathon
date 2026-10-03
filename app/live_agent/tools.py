"""Tool implementations for EvidenceTrail investigator agent.
Tools generate stable evidence records stored before returning to the model.
"""

from typing import Dict, Any, List, Optional
import datetime
import json

class EvidenceStore:
    def __init__(self):
        self.evidence_list: List[Dict[str, Any]] = []
        self._counter = 1

    def add(self, evidence_type: str, source: str, source_record_id: str, payload: Dict[str, Any], title: str, summary: str) -> Dict[str, Any]:
        evidence_id = f"E{self._counter:02d}"
        self._counter += 1
        record = {
            "evidence_id": evidence_id,
            "type": evidence_type,
            "source": source,
            "source_record_id": source_record_id,
            "title": title,
            "summary": summary,
            "payload": payload,
            "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.evidence_list.append(record)
        return record

    def get_all(self) -> List[Dict[str, Any]]:
        return self.evidence_list

    def get_by_id(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        for e in self.evidence_list:
            if e["evidence_id"] == evidence_id:
                return e
        return None


class InvestigationEnvironment:
    """Provides sandboxed tool executions for a given scenario snapshot."""
    
    def __init__(self, scenario: Dict[str, Any], evidence_store: EvidenceStore, patches: Optional[Dict[str, Any]] = None):
        self.scenario = scenario
        self.evidence_store = evidence_store
        self.patches = patches or {}

    def get_behavior_profile(self, customer_id: str) -> Dict[str, Any]:
        cust = self.scenario["customer"]
        tx = self.scenario["transaction"]
        amount = tx["amount"]
        is_outside_range = amount < cust["typical_min"] or amount > cust["typical_max"]
        is_known_rec = tx["recipient_id"] in cust["known_recipients"]
        
        payload = {
            "customer_id": cust["id"],
            "account_age_years": round((datetime.datetime.now().year - int(cust["account_created"][:4])), 1),
            "typical_range_sek": f"{cust['typical_min']} - {cust['typical_max']}",
            "current_tx_amount": amount,
            "is_outside_typical_range": is_outside_range,
            "is_known_recipient": is_known_rec,
            "known_recipients_count": len(cust["known_recipients"])
        }
        summary = (
            f"Transaction amount {amount} SEK is "
            f"{'OUTSIDE' if is_outside_range else 'WITHIN'} typical range ({cust['typical_min']}-{cust['typical_max']} SEK). "
            f"Recipient is {'KNOWN' if is_known_rec else 'NEW (never transacted before)'}."
        )
        evidence = self.evidence_store.add(
            evidence_type="customer_behavior",
            source="core_banking_ledger",
            source_record_id=customer_id,
            payload=payload,
            title=f"Customer Behavior Profile: {cust['name']}",
            summary=summary
        )
        return {
            "status": "success",
            "evidence_id": evidence["evidence_id"],
            "summary": summary,
            "data": payload
        }

    def inspect_device(self, transaction_id: str) -> Dict[str, Any]:
        dev = self.scenario["device"]
        tx = self.scenario["transaction"]
        payload = {
            "transaction_id": tx["id"],
            "device_id": dev["id"],
            "is_trusted_known_device": dev["is_known"],
            "os_environment": dev["os"],
            "auth_type": tx["auth_type"],
            "session_anomalies": dev["session_anomalies"],
            "has_anomalies": len(dev["session_anomalies"]) > 0
        }
        if len(dev["session_anomalies"]) > 0:
            summary = f"Anomalous session detected on device {dev['id']}: {'; '.join(dev['session_anomalies'])}"
        elif dev["is_known"]:
            summary = f"Device {dev['id']} is a known trusted device ({dev['os']}) with zero telemetry anomalies."
        else:
            summary = f"New unrecognized device {dev['id']} ({dev['os']}) without active compromise anomalies."

        evidence = self.evidence_store.add(
            evidence_type="device_telemetry",
            source="mobile_sdk_telemetry",
            source_record_id=dev["id"],
            payload=payload,
            title=f"Device Telemetry: {dev['id']}",
            summary=summary
        )
        return {
            "status": "success",
            "evidence_id": evidence["evidence_id"],
            "summary": summary,
            "data": payload
        }

    def inspect_recipient(self, recipient_id: str) -> Dict[str, Any]:
        rec = self.scenario["recipient"]
        
        # Apply patch if counterfactual removes suspicious flags
        synthetic_flags = list(rec["synthetic_flags"])
        incoming_rate = rec["incoming_transfers_90min"]
        if self.patches.get("remove_suspicious_network"):
            synthetic_flags = []
            incoming_rate = 1

        payload = {
            "recipient_id": rec["id"],
            "name": rec["name"],
            "account_age_days": rec["account_age_days"],
            "incoming_transfers_90min": incoming_rate,
            "total_incoming_today_sek": rec["total_incoming_volume_today"],
            "synthetic_flags": synthetic_flags,
            "is_high_velocity_mule": incoming_rate >= 10
        }
        summary = (
            f"Recipient {rec['name']} account created {rec['account_age_days']} days ago. "
            f"Incoming transfer velocity: {incoming_rate} transfers in past 90 min. "
            f"Flags: {', '.join(synthetic_flags) if synthetic_flags else 'None'}."
        )
        evidence = self.evidence_store.add(
            evidence_type="recipient_record",
            source="interbank_settlement_registry",
            source_record_id=recipient_id,
            payload=payload,
            title=f"Recipient Intelligence: {rec['name']}",
            summary=summary
        )
        return {
            "status": "success",
            "evidence_id": evidence["evidence_id"],
            "summary": summary,
            "data": payload
        }

    def search_relationship_graph(self, recipient_id: str, max_hops: int = 2) -> Dict[str, Any]:
        graph_data = self.scenario["graph"]
        nodes = list(graph_data["nodes"])
        links = list(graph_data["links"])

        # Counterfactual patch: remove flagged accounts and shared devices
        if self.patches.get("remove_suspicious_network"):
            nodes = [n for n in nodes if n["risk"] not in ("critical", "high") or n["type"] == "customer"]
            # Keep only links between remaining nodes
            remaining_ids = {n["id"] for n in nodes}
            links = [l for l in links if l["source"] in remaining_ids and l["target"] in remaining_ids]

        flagged_nodes = [n for n in nodes if n.get("risk") in ("high", "critical")]
        has_network_suspicion = len(flagged_nodes) > 0

        payload = {
            "search_root": recipient_id,
            "max_hops_explored": max_hops,
            "nodes_count": len(nodes),
            "links_count": len(links),
            "flagged_nodes": [f"{n['label']} ({n['id']})" for n in flagged_nodes],
            "graph_snapshot": {"nodes": nodes, "links": links}
        }
        if has_network_suspicion:
            summary = (
                f"Relationship graph detected 2-hop connection from recipient to {len(flagged_nodes)} "
                f"flagged entities: {', '.join(payload['flagged_nodes'])} via shared device fingerprints."
            )
        else:
            summary = "Relationship graph search completed: No connection to known mule networks or flagged devices found within 2 hops."

        evidence = self.evidence_store.add(
            evidence_type="network_graph",
            source="graph_entity_resolution",
            source_record_id=recipient_id,
            payload=payload,
            title="Entity Relationship Graph (2 Hops)",
            summary=summary
        )
        return {
            "status": "success",
            "evidence_id": evidence["evidence_id"],
            "summary": summary,
            "data": payload
        }

    def assess_with_jev(self, evidence_ids: List[str]) -> Dict[str, Any]:
        """TypeSafe Jev Structured Judgment Tool.
        Synthesizes state from accumulated evidence and returns typed judgment.
        """
        # Collect valid evidence payloads
        referenced_evidence = [self.evidence_store.get_by_id(eid) for eid in evidence_ids if self.evidence_store.get_by_id(eid)]
        
        # Analyze current evidence types
        types_present = {e["type"] for e in referenced_evidence}
        
        # Check for device anomalies
        device_anomalies = False
        for e in referenced_evidence:
            if e["type"] == "device_telemetry" and e["payload"].get("has_anomalies"):
                device_anomalies = True

        # Check for recipient / graph anomalies
        network_flagged = False
        mule_velocity = False
        for e in referenced_evidence:
            if e["type"] == "network_graph" and len(e["payload"].get("flagged_nodes", [])) > 0:
                network_flagged = True
            if e["type"] == "recipient_record" and e["payload"].get("is_high_velocity_mule"):
                mule_velocity = True

        # Check for customer inquiry statement (from Question Bank response)
        customer_coerced = False
        customer_voluntary = False
        customer_statement_text = None
        for e in referenced_evidence:
            if e["type"] == "customer_inquiry_statement":
                verdict = e["payload"].get("risk_verdict")
                customer_statement_text = e["payload"].get("customer_statement")
                if verdict in ("CONFIRMED_COERCION", "CONFIRMED_ATO", "INVESTMENT_TRAP", "SUSPECTED_INVOICE_INTERCEPTION"):
                    customer_coerced = True
                elif verdict in ("VOLUNTARY_UNCOERCED", "AUTHORIZED_LEGITIMATE", "VERIFIED_SUPPLIER"):
                    customer_voluntary = True

        # Determine Jev typed fields according to spec
        if customer_coerced:
            recipient_risk = "CRITICAL"
            manipulation_indicators = True
            payer_status = "CONFIRMED_COERCED_VICTIM"
            sufficiency = "DECISIVE_GROUNDED"
            next_step = "FREEZE_IN_ESCROW"
            risk_score = 0.99
            dossier_brief = f"Customer testimony decisively confirmed manipulation: '{customer_statement_text}'. Counterparty mule indicators corroborated. Escalate to Financial Crime Team."
        elif customer_voluntary and not network_flagged and not mule_velocity:
            recipient_risk = "LOW"
            manipulation_indicators = False
            payer_status = "VERIFIED_VOLUNTARY"
            sufficiency = "DECISIVE_GROUNDED"
            next_step = "RELEASE_ESCROW"
            risk_score = 0.05
            dossier_brief = "Customer confirmed legitimate voluntary transfer without social engineering indicators. Clear to release."
        elif customer_voluntary and (network_flagged or mule_velocity):
            recipient_risk = "HIGH"
            manipulation_indicators = False
            payer_status = "VOLUNTARY_BUT_MULE_RISK"
            sufficiency = "SUFFICIENT_FOR_RECOMMENDATION"
            next_step = "MANDATORY_ADVISOR_WARNING"
            risk_score = 0.75
            dossier_brief = "Customer claims voluntary intent, but counterparty exhibits severe mule cluster ties. Out-of-band specialist intervention required."
        elif network_flagged or (mule_velocity and not self.patches.get("remove_suspicious_network")):
            recipient_risk = "HIGH"
            manipulation_indicators = True
            payer_status = "SUSPECTED_MANIPULATED_PAYER"
            sufficiency = "SUFFICIENT_FOR_RECOMMENDATION"
            next_step = "CUSTOMER_CONTEXT_INQUIRY"
            risk_score = 0.89
            dossier_brief = "Technical ledger patterns suggest active APP safe account scam. Payer interview needed to confirm coercion."
        elif device_anomalies:
            recipient_risk = "ELEVATED"
            manipulation_indicators = False
            payer_status = "SUSPECTED_SESSION_TAKEOVER"
            sufficiency = "SUFFICIENT_FOR_RECOMMENDATION"
            next_step = "OUT_OF_BAND_DEVICE_CHALLENGE"
            risk_score = 0.82
            dossier_brief = "Headless browser / impossible travel telemetry. Account credentials compromised."
        elif len(types_present) >= 3:
            recipient_risk = "LOW"
            manipulation_indicators = False
            payer_status = "BENIGN_ROUTINE"
            sufficiency = "SUFFICIENT_FOR_RECOMMENDATION"
            next_step = "FINISH"
            risk_score = 0.08
            dossier_brief = "Baseline verified within historical customer tolerance. Zero anomalies detected."
        else:
            recipient_risk = "UNKNOWN"
            manipulation_indicators = False
            payer_status = "INSUFFICIENT_DATA"
            sufficiency = "NEED_MORE_EVIDENCE"
            next_step = "CHECK_GRAPH" if "network_graph" not in types_present else "CHECK_RECIPIENT"
            risk_score = 0.45
            dossier_brief = "Initial screening incomplete. Additional evidentiary hops required."

        payload = {
            "jev_model_version": "jev-reasoner-v1.4",
            "evaluated_evidence_ids": evidence_ids,
            "recipient_risk": recipient_risk,
            "payer_status": payer_status,
            "evidence_sufficiency": sufficiency,
            "suggested_next_step": next_step,
            "manipulation_indicators_detected": manipulation_indicators,
            "normalized_risk_score": risk_score,
            "dossier_brief": dossier_brief
        }
        summary = (
            f"Jev Structured Assessment: Recipient Risk is {recipient_risk}. "
            f"Payer Status: {payer_status}. "
            f"Sufficiency: {sufficiency}. "
            f"Manipulation Indicators: {'DETECTED' if manipulation_indicators else 'NONE'}."
        )
        evidence = self.evidence_store.add(
            evidence_type="jev_assessment",
            source="typesafe_jev_service",
            source_record_id="jev-run-live",
            payload=payload,
            title="TypeSafe Jev Structured Judgment",
            summary=summary
        )
        return {
            "status": "success",
            "evidence_id": evidence["evidence_id"],
            "summary": summary,
            "data": payload
        }

    def record_customer_inquiry_response(self, question_id: str, selected_option: Dict[str, Any]) -> Dict[str, Any]:
        """Ingests customer response from Question Bank or Google Voice into Evidence Store as E07."""
        channel = selected_option.get("interrogation_channel") or selected_option.get("audio_source") or "Google_Voice_Interrogation"
        payload = {
            "question_id": question_id,
            "selected_option_key": selected_option.get("key", "UNKNOWN"),
            "customer_statement": selected_option.get("statement", ""),
            "risk_verdict": selected_option.get("risk_verdict", "CONFIRMED_COERCED_VICTIM"),
            "recommended_action": selected_option.get("recommended_action", "PROTECTIVE_ESCROW_HOLD"),
            "interrogation_channel": channel
        }
        lbl = selected_option.get("label", "Voice Testimony")
        stmt = selected_option.get("statement", "")
        summary = f"Customer Statement Recorded via {channel}: '{lbl}'. Finding: {stmt}"
        evidence = self.evidence_store.add(
            evidence_type="customer_inquiry_statement",
            source="bank_voice_customer_interrogation",
            source_record_id=question_id,
            payload=payload,
            title=f"Customer Voice Inquiry: {selected_option.get('risk_verdict', 'CONFIRMED_COERCION')}",
            summary=summary
        )
        return {
            "status": "success",
            "evidence_id": evidence["evidence_id"],
            "summary": summary,
            "data": payload
        }
