"""Recorded audit trail: ordered events with a simple hash chain.

This is a stored log of observable calls and brief justifications. It is not
claimed to be immutable or compliance certified.
"""

import uuid

from .canon import now_utc, redact, sha256

EVENT_FIELDS = (
    "event_type", "actor", "tool_name", "validated_arguments", "input_evidence_ids",
    "output_evidence_ids", "result_snapshot", "reason_code", "brief_justification",
    "provider", "requested_model", "returned_model_version", "generation_settings",
    "duration_ms", "usage_if_available", "error",
)


class TraceRecorder:
    def __init__(self, run_id, case_id, context):
        self.run_id = run_id
        self.case_id = case_id
        self.context = context  # prompt_version, policy_version, ...
        self.events = []
        self._prev = None

    def record(self, **fields) -> dict:
        event = {
            "trace_id": uuid.uuid4().hex[:12],
            "run_id": self.run_id,
            "case_id": self.case_id,
            "sequence": len(self.events) + 1,
            "timestamp_utc": now_utc(),
            "prompt_version": self.context.get("prompt_version"),
            "policy_version": self.context.get("policy_version"),
        }
        for name in EVENT_FIELDS:
            event[name] = fields.get(name)
        for name in ("validated_arguments", "result_snapshot", "generation_settings", "usage_if_available"):
            event[name] = redact(event[name])
        event["input_evidence_ids"] = event["input_evidence_ids"] or []
        event["output_evidence_ids"] = event["output_evidence_ids"] or []
        event["previous_event_hash"] = self._prev
        event["event_hash"] = sha256({k: v for k, v in event.items() if k != "event_hash"})
        self._prev = event["event_hash"]
        self.events.append(event)
        return event


def verify_chain(events) -> bool:
    prev = None
    for e in events:
        body = {k: v for k, v in e.items() if k != "event_hash"}
        if e["previous_event_hash"] != prev or sha256(body) != e["event_hash"]:
            return False
        prev = e["event_hash"]
    return True
