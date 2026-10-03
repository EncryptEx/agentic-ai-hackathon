"""Synthetic scenarios. Everything here is synthetic data.

The agent only ever sees `transaction` (via the run) and whatever the tools return
from `world`. Display names live here; expected labels live only in eval_fixtures.py.
"""

import copy

from .config import SCENARIO_VERSION

_T = "2026-10-03T09:41:00Z"


def _prov(record):
    return {"source": "synthetic_graph_store", "record_id": record, "observed_at": _T}


def _case(case_id, name, tx, behavior, device, recipients, graph=None, tool_failures=()):
    return {
        "case_id": case_id,
        "name": name,
        "synthetic": True,
        "transaction": tx,
        "world": {
            "behavior": behavior,
            "device": device,
            "recipients": recipients,
            "graph": graph or {},
            "tool_failures": list(tool_failures),
        },
    }


def _tx(txid, cust, rid, amount, ref, channel="mobile_app"):
    return {
        "transaction_id": txid, "customer_id": cust, "recipient_id": rid,
        "amount": amount, "currency": "SEK", "timestamp": _T,
        "channel": channel, "payment_reference": ref,
    }


def _behavior(known, lo=200, hi=2000, summary="Regular small payments and bills."):
    return {"currency": "SEK", "typical_amount_min": lo, "typical_amount_max": hi,
            "known_recipient_ids": known, "history_summary": summary}


def _recipient(rid, age_days, incoming_90min, flags=0):
    return {"recipient_id": rid, "account_age_days": age_days,
            "incoming_transfers_last_90_min": incoming_90min, "prior_synthetic_flags": flags}


_EMPTY_GRAPH = {"nodes": [], "links": []}

_CASES = [
    _case(
        "case-familiar", "Familiar payment",
        _tx("TX-1001", "CUST-A101", "RCP-501", 600, "Rent share"),
        _behavior(["RCP-501", "RCP-502"]),
        {"device_known": True, "authentication": "normal", "session_anomalies": []},
        {"RCP-501": _recipient("RCP-501", 1450, 2)},
        {"RCP-501": _EMPTY_GRAPH},
    ),
    _case(
        "case-takeover", "Possible account takeover",
        _tx("TX-1002", "CUST-A102", "RCP-601", 8000, "Invoice 4471"),
        _behavior(["RCP-502", "RCP-503"]),
        {"device_known": False, "authentication": "password_reset_then_login",
         "session_anomalies": [{"type": "remote_access_tool_detected", "severity": "meaningful"},
                               {"type": "login_from_new_country", "severity": "minor"}]},
        {"RCP-601": _recipient("RCP-601", 210, 1)},
        {"RCP-601": _EMPTY_GRAPH},
    ),
    _case(
        "case-manipulated", "Manipulated payer",
        _tx("TX-1003", "CUST-A103", "RCP-701", 24500, "Investment opportunity"),
        _behavior(["RCP-504"]),
        {"device_known": True, "authentication": "normal", "session_anomalies": []},
        {"RCP-701": _recipient("RCP-701", 3, 14, flags=0)},
        {"RCP-701": {
            "nodes": [{"id": "RCP-701", "kind": "recipient", "synthetic_flag": False},
                      {"id": "DEV-X9", "kind": "device", "synthetic_flag": False},
                      {"id": "ACC-FLAG-88", "kind": "account", "synthetic_flag": True}],
            "links": [{"from": "RCP-701", "to": "DEV-X9", "via": "shared_device", "hops": 1,
                       "provenance": _prov("GL-9001")},
                      {"from": "DEV-X9", "to": "ACC-FLAG-88", "via": "shared_device", "hops": 2,
                       "provenance": _prov("GL-9002")}]}},
    ),
    _case(
        "case-legit-high", "Legitimate high-value purchase",
        _tx("TX-1004", "CUST-A104", "RCP-505", 15000, "Sofa order 88231"),
        _behavior(["RCP-505", "RCP-506"], summary="Occasional furniture and electronics purchases."),
        {"device_known": True, "authentication": "normal", "session_anomalies": []},
        {"RCP-505": _recipient("RCP-505", 2900, 3)},
        {"RCP-505": _EMPTY_GRAPH},
    ),
    _case(
        "case-missing-tool", "Missing tool response",
        _tx("TX-1005", "CUST-A105", "RCP-507", 700, "Gift"),
        _behavior(["RCP-507"]),
        {"device_known": True, "authentication": "normal", "session_anomalies": []},
        {"RCP-507": _recipient("RCP-507", 800, 1)},
        {"RCP-507": _EMPTY_GRAPH},
        tool_failures=["inspect_recipient"],
    ),
]

SCENARIOS = {c["case_id"]: c for c in _CASES}


def get_case(case_id):
    case = SCENARIOS.get(case_id)
    return copy.deepcopy(case) if case else None


def list_scenarios():
    """Names and initial transaction only."""
    return [{"case_id": c["case_id"], "name": c["name"], "synthetic": True,
             "scenario_version": SCENARIO_VERSION, "transaction": copy.deepcopy(c["transaction"])}
            for c in _CASES]


def apply_counterfactual(case, patch):
    """Clone a case with an evidence-change patch; the original is never mutated.

    patch keys (all optional):
      remove_network_links: bool  - drop recipient graph links and flagged nodes
      recipient: dict             - fields to overwrite on the recipient snapshot
    Related evidence is changed consistently: removing the network links also zeroes
    the recipient's prior synthetic flags.
    """
    clone = copy.deepcopy(case)
    clone["case_id"] = f"{case['case_id']}-cf"
    clone["name"] = f"{case['name']} (evidence-change experiment)"
    rid = clone["transaction"]["recipient_id"]
    world = clone["world"]
    if patch.get("remove_network_links"):
        world["graph"][rid] = {"nodes": [], "links": []}
        if rid in world["recipients"]:
            world["recipients"][rid]["prior_synthetic_flags"] = 0
    if isinstance(patch.get("recipient"), dict) and rid in world["recipients"]:
        world["recipients"][rid].update(patch["recipient"])
    clone["counterfactual_of"] = case["case_id"]
    clone["counterfactual_patch"] = copy.deepcopy(patch)
    return clone
