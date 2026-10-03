"""The five investigation tools plus the structured finish operation.

Tools read only from the case `world`; they cannot reveal scenario names or labels.
Arguments are validated against the run's transaction before execution.
"""

from collections import deque

from .config import MAX_GRAPH_HOPS

FINISH = "finish_investigation"
DATA_TOOLS = ("get_behavior_profile", "inspect_device", "inspect_recipient", "search_relationship_graph")
JEV_TOOL = "assess_with_jev"

TOOL_DECLARATIONS = [
    {"type": "function", "name": "get_behavior_profile",
     "description": "Typical amount range, known recipients and relevant history for a customer.",
     "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}},
                    "required": ["customer_id"]}},
    {"type": "function", "name": "inspect_device",
     "description": "Known/new device and simulated session anomalies for a transaction.",
     "parameters": {"type": "object", "properties": {"transaction_id": {"type": "string"}},
                    "required": ["transaction_id"]}},
    {"type": "function", "name": "inspect_recipient",
     "description": "Recipient account age, incoming transfer velocity and prior synthetic flags.",
     "parameters": {"type": "object", "properties": {"recipient_id": {"type": "string"}},
                    "required": ["recipient_id"]}},
    {"type": "function", "name": "search_relationship_graph",
     "description": "Bounded links from the recipient through accounts/devices, each with provenance. Max 2 hops.",
     "parameters": {"type": "object",
                    "properties": {"recipient_id": {"type": "string"},
                                   "max_hops": {"type": "integer", "minimum": 1, "maximum": MAX_GRAPH_HOPS}},
                    "required": ["recipient_id", "max_hops"]}},
    {"type": "function", "name": JEV_TOOL,
     "description": "Structured Jev judgment over evidence already gathered in this run.",
     "parameters": {"type": "object",
                    "properties": {"evidence_ids": {"type": "array", "items": {"type": "string"}}},
                    "required": ["evidence_ids"]}},
    {"type": "function", "name": FINISH,
     "description": "Submit the final recommendation. This is a recommendation only; it moves no money.",
     "parameters": {"type": "object", "properties": {
         "recommended_action": {"type": "string", "enum": ["ALLOW", "CONTEXT_CHECK", "REVIEW"]},
         "status": {"type": "string", "enum": ["COMPLETE", "INCOMPLETE"]},
         "claims": {"type": "array", "items": {"type": "object", "properties": {
             "text": {"type": "string"},
             "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}}},
             "required": ["text", "supporting_evidence_ids"]}},
         "remaining_uncertainty": {"type": "string"},
         "reason_code": {"type": "string"}},
         "required": ["recommended_action", "status", "claims", "remaining_uncertainty"]}},
]


_REASON = {"type": "string", "description": "One short plain-language sentence a bank investigator would "
                                            "understand: why you are making this check."}
for _decl in TOOL_DECLARATIONS:
    if _decl["name"] != FINISH:
        _decl["parameters"]["properties"]["reason"] = _REASON  # optional, deliberately not in "required"


class ToolError(Exception):
    """Argument validation or lookup failure; becomes a visible tool_error evidence record."""


def _require(args, key, type_):
    value = args.get(key)
    ok = isinstance(value, type_) and not (type_ is int and isinstance(value, bool))
    if not ok:
        raise ToolError(f"invalid or missing argument '{key}'")
    return value


def validate_arguments(name, args, case):
    """Return validated arguments or raise ToolError. Binds ids to this run's transaction."""
    if not isinstance(args, dict):
        raise ToolError("arguments must be an object")
    tx = case["transaction"]
    if name == "get_behavior_profile":
        cid = _require(args, "customer_id", str)
        if cid != tx["customer_id"]:
            raise ToolError("customer_id does not match this investigation")
        return {"customer_id": cid}
    if name == "inspect_device":
        tid = _require(args, "transaction_id", str)
        if tid != tx["transaction_id"]:
            raise ToolError("transaction_id does not match this investigation")
        return {"transaction_id": tid}
    if name == "inspect_recipient":
        rid = _require(args, "recipient_id", str)
        if rid != tx["recipient_id"]:
            raise ToolError("recipient_id does not match this investigation")
        return {"recipient_id": rid}
    if name == "search_relationship_graph":
        rid = _require(args, "recipient_id", str)
        hops = _require(args, "max_hops", int)
        if rid != tx["recipient_id"]:
            raise ToolError("recipient_id does not match this investigation")
        if not 1 <= hops <= MAX_GRAPH_HOPS:
            raise ToolError(f"max_hops must be between 1 and {MAX_GRAPH_HOPS}")
        return {"recipient_id": rid, "max_hops": hops}
    if name == JEV_TOOL:
        ids = _require(args, "evidence_ids", list)
        if not ids or not all(isinstance(i, str) for i in ids):
            raise ToolError("evidence_ids must be a non-empty list of strings")
        return {"evidence_ids": ids}
    raise ToolError(f"unknown tool '{name}'")


def execute_data_tool(name, args, case):
    """Run one of the four data tools. Returns (evidence_type, source_record_id, payload)."""
    world = case["world"]
    if name in world.get("tool_failures", []):
        raise ToolError(f"{name} returned no response (simulated provider failure)")
    tx = case["transaction"]
    if name == "get_behavior_profile":
        return "behavior_profile", tx["customer_id"], dict(world["behavior"])
    if name == "inspect_device":
        return "device_inspection", tx["transaction_id"], dict(world["device"])
    if name == "inspect_recipient":
        rec = world["recipients"].get(args["recipient_id"])
        if rec is None:
            raise ToolError("recipient not found")
        return "recipient_inspection", args["recipient_id"], dict(rec)
    if name == "search_relationship_graph":
        return "relationship_graph", args["recipient_id"], _graph(world, args["recipient_id"], args["max_hops"])
    raise ToolError(f"'{name}' is not a data tool")


def _graph(world, rid, max_hops):
    g = world["graph"].get(rid, {"nodes": [], "links": []})
    nodes = {n["id"]: n for n in g["nodes"]}
    reached, seen = [], {rid}
    queue = deque([(rid, 0)])
    while queue:
        cur, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for link in g["links"]:
            if link["from"] == cur and link["to"] not in seen:
                seen.add(link["to"])
                reached.append(link)
                queue.append((link["to"], depth + 1))
    flagged = sorted(i for i in seen if nodes.get(i, {}).get("synthetic_flag"))
    return {"recipient_id": rid, "max_hops": max_hops,
            "nodes": [nodes[i] for i in sorted(seen) if i in nodes],
            "links": reached,
            "synthetically_flagged_node_ids": flagged,
            "note": "Links are indicators, not proof of criminality."}
