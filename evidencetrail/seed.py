"""Investigate transactions from the project's FRAML data seed (data/kyc_aml.db).

Builds the same `case` structure as the hand-built scenarios, so the agents, Jev, policy, G-Eval and
alerts run unchanged. Everything is derived from observable fields and is TIME-CAUSAL: for a
transaction at time T only data strictly before T is used (customer history, other customers' activity,
rule-engine alerts raised from earlier transactions).

The data generator's fraud and suspicious flags and typology tags are its answer key. They are never
selected here; a separate evaluator-only module reads them. Device IDs are
pseudonymised because a seed identifier such as 'DEV-BOTNET-CLONE-441' would name the fraud.

Thresholds below are principled constants, not tuned to the labels.
"""

import bisect
import hashlib
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta

DEFAULT_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "kyc_aml.db"))
CASE_PREFIX = "seed:"

MICRO_USD = 5.0                 # charges below this are treated as card-testing sized
MICRO_WINDOW = timedelta(minutes=30)
TRAVEL_WINDOW = timedelta(hours=3)   # a country change faster than this is a meaningful anomaly
SHARED_DEVICE_MEANINGFUL = 2    # other customers seen on a device before T
KNOWN_DEVICE_MIN_AGE = timedelta(hours=24)  # a device first seen minutes ago (e.g. by the attack itself) is not familiar
VELOCITY_WINDOW = timedelta(minutes=90)
HISTORY_MIN = 5                 # prior outbound transactions needed for a behavioural range
GRAPH_MAX_PAYERS = 8
FLAG_SEVERITIES = ("HIGH", "CRITICAL")
FLAG_RATIO = 0.25               # association with flagged payers counts only above this share of a recipient's payers

# Only these columns are ever read. Label columns are deliberately absent.
_TX_COLUMNS = ("transaction_id", "customer_id", "timestamp", "transaction_type", "direction", "amount_usd",
               "currency", "counterparty_name", "counterparty_country", "counterparty_category", "channel",
               "reference_narrative", "device_id", "ip_country", "auth_status", "card_entry_mode",
               "is_new_payee", "payee_first_seen_hours")
_CUSTOMER_COLUMNS = ("customer_id", "device_primary_id", "primary_ip_country", "declared_expected_max_single_tx_usd",
                     "declared_expected_monthly_turnover_usd")


def slug(text):
    return re.sub(r"[^A-Z0-9]+", "-", (text or "").upper()).strip("-") or "UNKNOWN"


def recipient_id(counterparty_name):
    return "RCP-" + slug(counterparty_name)


def pseudo(prefix, value):
    return f"{prefix}-{hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:6].upper()}"


def percentile(sorted_values, p):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def _dt(text):
    return datetime.fromisoformat(text)


class SeedData:
    """Read-only, lazily loaded index over the seed database."""

    def __init__(self, path=None):
        self.path = path or os.environ.get("EVIDENCETRAIL_SEED_DB") or DEFAULT_DB
        self._lock = threading.Lock()
        self._loaded = False

    def available(self):
        return os.path.exists(self.path)

    def _load(self):
        with self._lock:
            if self._loaded:
                return
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                rows = [dict(r) for r in conn.execute(f"SELECT {', '.join(_TX_COLUMNS)} FROM transactions")]
                customers = {r["customer_id"]: dict(r) for r in conn.execute(
                    f"SELECT {', '.join(_CUSTOMER_COLUMNS)} FROM customers")}
                alerts = [dict(r) for r in conn.execute(
                    "SELECT customer_id, rule_id, severity, supporting_transaction_ids FROM alerts")]
            finally:
                conn.close()
            for r in rows:
                r["dt"] = _dt(r["timestamp"])
            rows.sort(key=lambda r: (r["dt"], r["transaction_id"]))
            self.by_id = {r["transaction_id"]: r for r in rows}
            self.by_customer, self.by_counterparty, self.by_device = {}, {}, {}
            for r in rows:
                self.by_customer.setdefault(r["customer_id"], []).append(r)
                if r["direction"] == "OUTBOUND":
                    self.by_counterparty.setdefault(r["counterparty_name"], []).append(r)
                if r["device_id"]:
                    self.by_device.setdefault(r["device_id"], []).append(r)
            self.customers = customers
            self.flags = {}  # customer_id -> [(effective_from datetime or None, rule_id, severity)]
            for a in alerts:
                if a["severity"] not in FLAG_SEVERITIES:
                    continue
                ids = json.loads(a["supporting_transaction_ids"] or "[]")
                stamps = [self.by_id[i]["dt"] for i in ids if i in self.by_id]
                if stamps:
                    effective = max(stamps)             # known once its last supporting transaction happened
                elif a["rule_id"] == "FR-05":
                    effective = datetime.min            # profile-based synthetic-identity flag: known from onboarding
                else:
                    continue                            # no timing information: never used (avoids look-ahead)
                self.flags.setdefault(a["customer_id"], []).append((effective, a["rule_id"], a["severity"]))
            self._loaded = True

    # ------------------------------------------------------------------ queries
    def flagged_payers(self, name, t, customer_id):
        """Other payers of a recipient who were already flagged before t, and whether that association is
        meaningful. Guilt by association only counts when a sizeable SHARE of the payers is flagged: a utility
        paid by a hundred customers will always have some flagged payer, which says nothing about it."""
        payers = {r["customer_id"] for r in self._before(self.by_counterparty.get(name, []), t)
                  if r["customer_id"] != customer_id}
        flagged = sorted(p for p in payers if self.flagged_before(p, t))
        meaningful = bool(flagged) and len(flagged) / len(payers) >= FLAG_RATIO
        return flagged, len(payers), meaningful

    def flagged_before(self, customer_id, t):
        """True if a HIGH/CRITICAL rule-engine alert for the customer was already knowable before t."""
        return any(eff < t for eff, _, _ in self.flags.get(customer_id, []))

    @staticmethod
    def _before(rows, t):
        times = [r["dt"] for r in rows]
        return rows[:bisect.bisect_left(times, t)]

    def build_case(self, transaction_id):
        """Return a case dict for an OUTBOUND seed transaction, or None if unknown/not investigable."""
        self._load()
        tx = self.by_id.get(transaction_id)
        if tx is None or tx["direction"] != "OUTBOUND":
            return None
        t, cust = tx["dt"], tx["customer_id"]
        rid = recipient_id(tx["counterparty_name"])
        transaction = {
            "transaction_id": tx["transaction_id"], "customer_id": cust, "recipient_id": rid,
            "amount": round(tx["amount_usd"], 2), "currency": tx["currency"], "timestamp": tx["timestamp"],
            "channel": tx["channel"], "payment_reference": tx["reference_narrative"],
            "transaction_type": tx["transaction_type"], "recipient_name": tx["counterparty_name"],
            "recipient_category": tx["counterparty_category"], "recipient_country": tx["counterparty_country"],
        }
        return {
            "case_id": CASE_PREFIX + transaction_id,
            "name": f"{tx['transaction_type'].replace('_', ' ').title()} {tx['amount_usd']:,.2f} {tx['currency']} to {tx['counterparty_name']}",
            "synthetic": True, "source": "seed", "transaction": transaction,
            "world": {"behavior": self._behavior(tx), "device": self._device(tx),
                      "recipients": {rid: self._recipient(tx)}, "graph": {rid: self._graph(tx, rid)},
                      "tool_failures": []},
        }

    # ------------------------------------------------------------------ evidence builders
    def _behavior(self, tx):
        t, cust = tx["dt"], tx["customer_id"]
        history = self._before(self.by_customer[cust], t)
        out = [r for r in history if r["direction"] == "OUTBOUND"]
        amounts = sorted(r["amount_usd"] for r in out)
        profile = self.customers.get(cust, {})
        declared_max = profile.get("declared_expected_max_single_tx_usd")
        if len(amounts) >= HISTORY_MIN:
            lo, hi = percentile(amounts, 0.05), percentile(amounts, 0.95)
            basis = f"5th-95th percentile of {len(amounts)} prior outbound transactions"
        else:
            lo, hi = 0.0, float(declared_max or 0.0)
            basis = f"only {len(amounts)} prior outbound transactions; using the declared maximum single transaction"
        inbound = [r for r in history if r["direction"] == "INBOUND" and t - r["dt"] <= timedelta(hours=48)]
        kinds = {}
        for r in out:
            kinds[r["transaction_type"]] = kinds.get(r["transaction_type"], 0) + 1
        return {
            "currency": "USD", "typical_amount_min": round(lo, 2), "typical_amount_max": round(hi, 2),
            "known_recipient_ids": sorted({recipient_id(r["counterparty_name"]) for r in out}),
            "history_summary": (f"{len(out)} prior outbound transactions before this transfer"
                                + (f"; median {percentile(amounts, 0.5):,.2f} USD" if amounts else "")
                                + (f"; types: {', '.join(f'{k} x{v}' for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]))}" if kinds else "")),
            "range_basis": basis, "declared_max_single_transaction": declared_max,
            "declared_monthly_turnover": profile.get("declared_expected_monthly_turnover_usd"),
            "recent_inbound_48h": {"count": len(inbound), "total_usd": round(sum(r["amount_usd"] for r in inbound), 2),
                                   "largest_usd": round(max((r["amount_usd"] for r in inbound), default=0.0), 2),
                                   "types": sorted({r["transaction_type"] for r in inbound})},
        }

    def _device(self, tx):
        t, cust, dev = tx["dt"], tx["customer_id"], tx["device_id"]
        if not dev:
            return {"telemetry_available": False,
                    "note": "This channel carries no device telemetry; absence is not reassuring or alarming by itself.",
                    "authorization_status": tx["auth_status"], "session_anomalies": []}
        profile = self.customers.get(cust, {})
        prior = [r for r in self._before(self.by_customer[cust], t) if r["transaction_id"] != tx["transaction_id"]]
        first_seen = {}
        for r in prior:
            if r["device_id"] and r["device_id"] not in first_seen:
                first_seen[r["device_id"]] = r["dt"]
        familiar = {d for d, ts in first_seen.items() if t - ts >= KNOWN_DEVICE_MIN_AGE} | {profile.get("device_primary_id")}
        prior_devices = set(first_seen) | {profile.get("device_primary_id")}
        device_first_seen_hours = round((t - first_seen[dev]).total_seconds() / 3600.0, 2) if dev in first_seen else None
        anomalies = []
        ip, home = tx["ip_country"], profile.get("primary_ip_country")
        if ip and home and ip != home:
            anomalies.append({"type": "ip_country_differs_from_profile", "severity": "minor",
                              "detail": f"session country {ip}, profile country {home}"})
        recent = next((r for r in reversed(prior) if r["ip_country"]), None)
        if ip and recent and recent["ip_country"] != ip and t - recent["dt"] <= TRAVEL_WINDOW:
            minutes = int((t - recent["dt"]).total_seconds() // 60)
            anomalies.append({"type": "rapid_country_change", "severity": "meaningful",
                              "detail": f"{recent['ip_country']} to {ip} within {minutes} minutes"})
        others = {r["customer_id"] for r in self._before(self.by_device.get(dev, []), t) if r["customer_id"] != cust}
        if len(others) >= SHARED_DEVICE_MEANINGFUL:
            anomalies.append({"type": "device_seen_on_other_customers", "severity": "meaningful",
                              "detail": f"this device was already used by {len(others)} other customers"})
        elif others:
            anomalies.append({"type": "device_seen_on_other_customers", "severity": "minor",
                              "detail": "this device was already used by 1 other customer"})
        micro_before = sum(1 for r in prior if r["device_id"] == dev and r["amount_usd"] < MICRO_USD
                           and t - r["dt"] <= MICRO_WINDOW)
        if tx["amount_usd"] < MICRO_USD and micro_before + 1 >= 2:
            anomalies.append({"type": "repeated_micro_charges", "severity": "meaningful",
                              "detail": f"{micro_before + 1} charges under {MICRO_USD:g} USD on this device within 30 minutes"})
        elif tx["amount_usd"] >= MICRO_USD and micro_before >= 2:
            anomalies.append({"type": "follows_micro_charge_probing", "severity": "meaningful",
                              "detail": f"{micro_before} charges under {MICRO_USD:g} USD on this device in the previous 30 minutes"})
        if tx["auth_status"] and tx["auth_status"].startswith("DECLINED"):
            anomalies.append({"type": "issuer_declined_as_suspected_fraud", "severity": "meaningful",
                              "detail": tx["auth_status"]})
        return {"telemetry_available": True, "device_known": dev in familiar,
                "device_first_seen_hours_ago": device_first_seen_hours,
                "device_ref": pseudo("DEV", dev), "devices_previously_used_by_customer": len(prior_devices - {None}),
                "ip_country": ip, "profile_ip_country": home,
                "authentication": f"{tx['channel']}" + (f" / {tx['card_entry_mode']}" if tx["card_entry_mode"] else ""),
                "authorization_status": tx["auth_status"], "session_anomalies": anomalies}

    def _recipient(self, tx):
        t, cust, name = tx["dt"], tx["customer_id"], tx["counterparty_name"]
        earlier = [r for r in self._before(self.by_counterparty.get(name, []), t) if r["transaction_id"] != tx["transaction_id"]]
        # A true account age exists only for new payees (payee_first_seen_hours). Otherwise the age is UNKNOWN:
        # "first seen in this 90-day window" is a truncated observation, not an age, and treating it as one makes
        # long-established recipients (e.g. a landlord paid by everyone at once) look newly created.
        if tx["payee_first_seen_hours"] is not None:
            age_days, basis = tx["payee_first_seen_hours"] / 24.0, "payee_first_seen_hours (explicit new-payee age)"
        else:
            age_days, basis = None, "unknown: no account age is recorded for this recipient"
        first_observed_days_ago = round((t - earlier[0]["dt"]).total_seconds() / 86400.0, 2) if earlier else None
        velocity = sum(1 for r in earlier if t - r["dt"] <= VELOCITY_WINDOW)
        flagged, n_payers, meaningful = self.flagged_payers(name, t, cust)
        return {"recipient_id": recipient_id(name), "account_age_days": None if age_days is None else round(age_days, 2),
                "first_observed_in_dataset_days_ago": first_observed_days_ago,
                "incoming_transfers_last_90_min": velocity, "prior_synthetic_flags": len(flagged) if meaningful else 0,
                "flagged_share_of_payers": f"{len(flagged)}/{n_payers}",
                "age_basis": basis, "distinct_other_payers_before": n_payers,
                "category": tx["counterparty_category"], "country": tx["counterparty_country"],
                "is_new_payee_for_customer": bool(tx["is_new_payee"]),
                "flag_basis": ("other payers with a HIGH/CRITICAL FRAML rule-engine alert already knowable before this "
                               f"transfer; counted only when at least {int(FLAG_RATIO * 100)}% of the recipient's payers are flagged")}

    def _graph(self, tx, rid):
        t, cust, name = tx["dt"], tx["customer_id"], tx["counterparty_name"]
        earlier = [r for r in self._before(self.by_counterparty.get(name, []), t) if r["customer_id"] != cust]
        latest = {}
        for r in earlier:                       # most recent paying transaction per other customer
            latest[r["customer_id"]] = r
        payers = sorted(latest.values(), key=lambda r: r["dt"], reverse=True)[:GRAPH_MAX_PAYERS]
        _, _, assoc = self.flagged_payers(name, t, cust)
        nodes = [{"id": rid, "kind": "recipient", "synthetic_flag": False}]
        links, seen = [], {rid}
        for r in payers:
            prov = {"source": "transactions", "record_id": r["transaction_id"], "observed_at": r["timestamp"]}
            if r["customer_id"] not in seen:
                seen.add(r["customer_id"])
                nodes.append({"id": r["customer_id"], "kind": "customer",
                              "synthetic_flag": assoc and self.flagged_before(r["customer_id"], t)})
            links.append({"from": rid, "to": r["customer_id"], "via": "also_paid_recipient", "hops": 1, "provenance": prov})
            if r["device_id"]:
                dref = pseudo("DEV", r["device_id"])
                if dref not in seen:
                    seen.add(dref)
                    nodes.append({"id": dref, "kind": "device", "synthetic_flag": False})
                links.append({"from": r["customer_id"], "to": dref, "via": "used_device", "hops": 2, "provenance": prov})
        return {"nodes": nodes, "links": links}

    # ------------------------------------------------------------------ candidate picker
    def candidates(self, controls_top=16, controls_random=15, seed=7):
        """A neutral mixed sample for manual testing: outbound transfers of types where attacks occur plus
        clean-looking controls. Labels are NOT used here to pick or order the list beyond the transaction types."""
        import random
        self._load()
        special = [r for r in self.by_id.values() if r["direction"] == "OUTBOUND" and r["transaction_type"] in (
            "P2P_TRANSFER_OUT", "INTERNATIONAL_WIRE_OUT", "CRYPTO_PURCHASE", "ONLINE_PURCHASE")]
        routine = sorted((r for r in self.by_id.values() if r["transaction_type"] in ("POS_PURCHASE", "ACH_WITHDRAWAL")),
                         key=lambda r: -r["amount_usd"])
        picked = special + routine[:controls_top]
        rest = routine[controls_top:]
        random.Random(seed).shuffle(rest)
        picked += rest[:controls_random]
        random.Random(seed + 1).shuffle(picked)     # order carries no information
        return [{"case_id": CASE_PREFIX + r["transaction_id"], "synthetic": True,
                 "name": f"{r['transaction_type'].replace('_', ' ').title()} {r['amount_usd']:,.2f} {r['currency']} to {r['counterparty_name']}",
                 "transaction": {"transaction_id": r["transaction_id"], "customer_id": r["customer_id"],
                                 "amount": round(r["amount_usd"], 2), "currency": r["currency"],
                                 "recipient_id": recipient_id(r["counterparty_name"]), "timestamp": r["timestamp"],
                                 "channel": r["channel"]}} for r in picked]


_default = SeedData()


def get_seed():
    return _default


def is_seed_case(case_id):
    return isinstance(case_id, str) and case_id.startswith(CASE_PREFIX)
