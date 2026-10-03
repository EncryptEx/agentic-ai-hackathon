"""Analyst alerts for finished investigations.

Jev triages each finished investigation (is it suspicious, and how urgent?) from the transaction
facts and recorded evidence, WITHOUT seeing the policy result. An alert is created when Jev finds
the case suspicious OR the deterministic policy routed it away from ALLOW. Jev can therefore raise
an alert on its own, but a "not suspicious" answer can never suppress a policy-raised alert.

An alert is a notification for an analyst. It moves and blocks no money, and it never changes the
simulated action, which stays with the policy engine. Jev probabilities are uncalibrated outputs.
"""

import json
import os
import sqlite3
import threading
import uuid

from .canon import canonical, now_utc, sha256
from .jev import ALERT_QUESTIONS, ALERT_SPEC_VERSION, ProviderUnavailable, build_state

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}
POLICY_SEVERITY = {"CONTEXT_CHECK": "medium", "REVIEW": "high"}
STATUSES = ("open", "acknowledged", "dismissed")
NOTICE = ("Alert for analyst attention on a synthetic case. No money is moved or blocked, and the alert "
          "does not change the simulated action. Jev outputs are uncalibrated model judgments.")
DEFAULT_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "evidencetrail.db"))


def triage_state(case, store) -> str:
    """Jev input: transaction facts plus recorded evidence. No case label, no policy outcome."""
    tx = case["transaction"]
    header = (f"TRANSACTION: amount={tx['amount']} {tx['currency']} channel={tx['channel']} "
              f"recipient_id={tx['recipient_id']} payment_reference(untrusted free text)={json.dumps(tx['payment_reference'])}")
    items = [e for e in store.all() if e["type"] not in ("tool_error", "jev_assessment", "alert_triage")]
    return header + "\nEVIDENCE:\n" + build_state(items)


def _level(score):
    try:
        return max(0, min(2, int(round(float(score)))))
    except (TypeError, ValueError):
        return None


def _jev_severity(level):
    return {0: "low", 1: "medium", 2: "high"}.get(level)


def _max_severity(*values):
    values = [v for v in values if v]
    return max(values, key=SEVERITY_RANK.get) if values else None


def run_triage(case, store, jev):
    """Ask Jev whether the case is suspicious. Returns (triage_dict, evidence_item_or_None).
    Unavailability stays visible as status 'unavailable'; nothing is fabricated."""
    data_items = [e for e in store.all() if e["type"] not in ("tool_error", "jev_assessment", "alert_triage")]
    if not data_items:
        triage = {"status": "skipped", "reason": "no evidence was gathered, so there is nothing to assess"}
        return triage, store.add("alert_triage", "alert_triage", None, triage)
    state = triage_state(case, store)
    try:
        result = jev.assess(state, questions=ALERT_QUESTIONS)
    except ProviderUnavailable as e:
        triage = {"status": "unavailable", "reason": str(e), "alert_spec_version": ALERT_SPEC_VERSION}
        return triage, store.add("alert_triage", "alert_triage", None, triage)
    norm = result["normalized"]
    level = _level(norm.get("severity"))
    suspicion = norm.get("suspicion")
    if suspicion not in ("SUSPICIOUS", "NOT_SUSPICIOUS", "UNDETERMINED"):
        triage = {"status": "error", "reason": f"unexpected suspicion value {suspicion!r}", "raw": result["raw"],
                  "alert_spec_version": ALERT_SPEC_VERSION}
        return triage, store.add("alert_triage", "alert_triage", None, triage)
    triage = {"status": "ok", "suspicion": suspicion, "severity_level": level, "model": result["model"],
              "usage": result["usage"], "raw": result["raw"], "state_hash": sha256(state),
              "alert_spec_version": ALERT_SPEC_VERSION,
              "note": "Probabilities are uncalibrated model outputs, not fraud probabilities."}
    return triage, store.add("alert_triage", "alert_triage", None, triage)


def decide_alert(triage, final):
    """Return (create, sources, disagreement). Jev can raise an alert; it can never suppress the policy's."""
    jev_flag = triage.get("status") == "ok" and triage.get("suspicion") == "SUSPICIOUS"
    policy_flag = final["status"] == "INCOMPLETE" or final["simulated_action"] != "ALLOW"
    sources = (["jev"] if jev_flag else []) + (["policy"] if policy_flag else [])
    disagreement = None
    if triage.get("status") != "ok":
        disagreement = "jev_unavailable"
    elif jev_flag and not policy_flag:
        disagreement = "jev_suspicious_policy_allow"
    elif policy_flag and triage.get("suspicion") == "NOT_SUSPICIOUS":
        disagreement = "policy_flagged_jev_not_suspicious"
    return bool(sources), sources, disagreement


def _title(final, sources):
    if final["status"] == "INCOMPLETE":
        return "Investigation incomplete: evidence missing"
    if "policy" not in sources:
        return "Jev flagged this transfer as suspicious"
    return {"REVIEW": "Transfer routed to review", "CONTEXT_CHECK": "Context check recommended"}[final["simulated_action"]]


def _summary(final, triage, sources, disagreement):
    parts = []
    signals = final.get("signals") or {}
    if signals:
        parts.append("Supported signals: " + "; ".join(f"{k.replace('_', ' ')} ({v['detail']})" for k, v in signals.items()) + ".")
    if final["status"] == "INCOMPLETE":
        parts.append(final["explanation"])
    if triage.get("status") == "ok":
        sev = _jev_severity(triage["severity_level"]) or "unrated"
        parts.append(f"Jev triage: {triage['suspicion'].replace('_', ' ').lower()}, severity {sev}.")
    else:
        parts.append(f"Jev triage {triage.get('status')}: {triage.get('reason')}.")
    if disagreement == "jev_suspicious_policy_allow":
        parts.append("Policy v1 would have allowed this transfer; the alert comes from Jev alone.")
    elif disagreement == "policy_flagged_jev_not_suspicious":
        parts.append("Jev did not find the case suspicious, but the policy routed it for attention, so the alert stands.")
    return " ".join(parts)


def build_alert(case, run_id, store, final, triage, triage_evidence):
    """Return an alert dict, or None when neither Jev nor the policy flagged the case."""
    create, sources, disagreement = decide_alert(triage, final)
    if not create:
        return None
    policy_sev = POLICY_SEVERITY.get(final["simulated_action"]) if "policy" in sources else None
    if final["status"] == "INCOMPLETE" and "policy" in sources:
        policy_sev = "high"  # routed to review for missing evidence
    jev_sev = _jev_severity(triage.get("severity_level")) if "jev" in sources else None
    evidence_ids = sorted({i for v in (final.get("signals") or {}).values() for i in v["evidence_ids"]}
                          | ({triage_evidence["evidence_id"]} if triage_evidence else set()))
    tx = case["transaction"]
    return {
        "alert_id": "ALT-" + uuid.uuid4().hex[:8].upper(), "run_id": run_id, "case_id": case["case_id"],
        "status": "open", "severity": _max_severity(policy_sev, jev_sev) or "low",
        "sources": sources, "disagreement": disagreement,
        "title": _title(final, sources), "summary": _summary(final, triage, sources, disagreement),
        "transaction": {k: tx[k] for k in ("transaction_id", "customer_id", "recipient_id", "amount", "currency")},
        "policy": {"action": final["simulated_action"], "status": final["status"], "rule": final["rule"],
                   "reason_code": final["reason_code"], "policy_version": final["policy_version"]},
        "jev_triage": {k: triage.get(k) for k in ("status", "suspicion", "severity_level", "model", "reason",
                                                  "alert_spec_version")},
        "evidence_ids": evidence_ids, "synthetic": True, "notice": NOTICE,
        "created_at": now_utc(), "handoff": None,
        "history": [{"status": "open", "at": now_utc(), "note": "Alert created"}],
    }


class AlertStore:
    """SQLite persistence in its own file, so the host's committed database and its batch-generated
    alerts table are never touched. Opens lazily on first use."""

    def __init__(self, path=None):
        self.path = path or os.environ.get("EVIDENCETRAIL_ALERT_DB") or DEFAULT_DB
        self._conn = None
        self._lock = threading.Lock()

    def _db(self):
        if self._conn is None:
            if self.path != ":memory:":
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS evidencetrail_alerts (
                alert_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, case_id TEXT NOT NULL, severity TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)""")
            self._conn.commit()
        return self._conn

    def create(self, alert):
        with self._lock:
            db = self._db()
            db.execute("INSERT INTO evidencetrail_alerts VALUES (?,?,?,?,?,?,?)",
                       (alert["alert_id"], alert["run_id"], alert["case_id"], alert["severity"], alert["status"],
                        alert["created_at"], canonical(alert)))
            db.commit()
        return alert

    def get(self, alert_id):
        with self._lock:
            row = self._db().execute("SELECT payload FROM evidencetrail_alerts WHERE alert_id=?", (alert_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, status=None, severity=None):
        sql, params = "SELECT payload FROM evidencetrail_alerts", []
        clauses = [c for c, v in (("status=?", status), ("severity=?", severity)) if v]
        params = [v for v in (status, severity) if v]
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        with self._lock:
            rows = self._db().execute(sql + " ORDER BY created_at DESC", params).fetchall()
        return [json.loads(r[0]) for r in rows]

    def set_handoff(self, alert_id, handoff):
        """Attach (or update) the ADK hand-off record. Never changes status or the simulated action."""
        alert = self.get(alert_id)
        if alert is None:
            return None
        alert["handoff"] = handoff
        with self._lock:
            db = self._db()
            db.execute("UPDATE evidencetrail_alerts SET payload=? WHERE alert_id=?", (canonical(alert), alert_id))
            db.commit()
        return alert

    def set_status(self, alert_id, status, note=None):
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        alert = self.get(alert_id)
        if alert is None:
            return None
        alert["status"] = status
        alert["history"].append({"status": status, "at": now_utc(), "note": (note or "")[:500]})
        with self._lock:
            db = self._db()
            db.execute("UPDATE evidencetrail_alerts SET status=?, payload=? WHERE alert_id=?",
                       (status, canonical(alert), alert_id))
            db.commit()
        return alert
