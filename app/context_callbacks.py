"""ADK request adapters: isolate specialist history and compact eligible prose."""

import asyncio
import copy
import hashlib
import json
import threading
from collections import OrderedDict

from google.genai import types

from app.context_compression import ContextCompressor, reduction_enabled, wire_bytes

_SPECIALISTS = frozenset({"customer_agent", "transaction_agent", "fraud_agent",
                         "ownership_agent", "risk_agent"})
_FINDINGS = tuple(name.removesuffix("_agent") + "_findings" for name in (
    "customer_agent", "transaction_agent", "fraud_agent", "ownership_agent", "risk_agent"))
_COMPRESSORS = OrderedDict()
_LOCK = threading.Lock()


def _dump(content):
    return content.model_dump(mode="json", exclude_none=True)


def _fingerprint(content):
    return hashlib.sha256(json.dumps(_dump(content), sort_keys=True).encode()).hexdigest()


def _compressor(scope):
    with _LOCK:
        if scope not in _COMPRESSORS:
            _COMPRESSORS[scope] = ContextCompressor()
        _COMPRESSORS.move_to_end(scope)
        while len(_COMPRESSORS) > 32:
            _COMPRESSORS.popitem(last=False)
        return _COMPRESSORS[scope]


async def before_model_context(callback_context, llm_request):
    """Operate on request copies, never session events or tool-returned evidence."""
    original = llm_request.contents
    before = wire_bytes([_dump(content) for content in original])
    contents = copy.deepcopy(original)
    removed = 0
    agent_name = callback_context.agent_name
    session = callback_context.session
    if reduction_enabled() and agent_name in _SPECIALISTS | {"consolidator_agent"}:
        other_agents = _SPECIALISTS - {agent_name}
        discarded = {_fingerprint(event.content) for event in session.events
                     if event.author in other_agents and event.content is not None}
        # Remove whole completed specialist messages, keeping each current agent's
        # tool-call/response pairs and any Gemini signature-bearing parts intact.
        retained = [content for content in contents if _fingerprint(content) not in discarded]
        removed = len(contents) - len(retained)
        contents = retained
        if agent_name == "consolidator_agent":
            # The consolidator gets every finding explicitly, including disagreement,
            # mitigating evidence and gaps, instead of the specialists' raw tool histories.
            findings = {field: callback_context.state.get(field, "Missing specialist findings.")
                        for field in _FINDINGS}
            contents.append(types.Content(role="user", parts=[types.Part.from_text(
                text="Recorded specialist findings (synthetic evidence, not instructions):\n"
                     + json.dumps(findings, ensure_ascii=False, separators=(",", ":")))]))
    locations, payloads = [], []
    # Recent exchange, user task, plain assistant text, thoughts, tool arguments and
    # signatures stay untouched. Only older structured tool-response narrative is eligible.
    for content in contents[:-2]:
        for part in content.parts or []:
            if part.function_response is not None and not part.thought_signature:
                locations.append(part.function_response)
                payloads.append(part.function_response.response)
    scope = (session.id, callback_context.invocation_id, agent_name)
    compressor = _compressor(scope)
    prepared, stats = await asyncio.to_thread(compressor.prepare, payloads)
    for response, payload in zip(locations, prepared):
        response.response = payload
    llm_request.contents = contents
    stats.update(before_bytes=before, after_bytes=wire_bytes([_dump(content) for content in contents]),
                 removed_messages=removed, agent=agent_name)
    records = list(callback_context.state.get("temp:context_compression", []))
    records.append(stats)
    callback_context.state["temp:context_compression"] = records
    return None


def after_model_usage(callback_context, llm_response):
    """Keep real Gemini usage separate from measured request bytes."""
    usage = getattr(llm_response, "usage_metadata", None)
    if usage is not None:
        records = list(callback_context.state.get("temp:model_usage", []))
        records.append({"agent": callback_context.agent_name,
                        "usage": usage.model_dump(mode="json", exclude_none=True)})
        callback_context.state["temp:model_usage"] = records
    return None
