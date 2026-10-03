"""ADK request adapters: isolate specialist history and compact eligible prose."""

import asyncio
import copy
import hashlib
import json
import re
import threading
from collections import OrderedDict

from google.genai import types

from app.context_compression import ContextCompressor, reduction_enabled, wire_bytes

_SPECIALISTS = frozenset({"customer_agent", "transaction_agent", "fraud_agent",
                         "ownership_agent", "risk_agent", "arbiter_agent"})
# session-state keys written by the agents' output_key; the consolidator gets all of them explicitly
_FINDINGS = ("customer_findings", "transaction_findings", "fraud_findings", "ownership_findings",
             "risk_findings", "tribunal_findings")
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


_HEADER = "For context:"
_OTHER_WORK = re.compile(r"^\[(\w+_agent)\] (?:called tool |`[^`]+` tool returned result)")
_OTHER_SAID = re.compile(r"^\[(\w+_agent)\] said:")


def _drop_other_transcripts(contents, agent_name):
    """ADK replays other agents' work as plain-text user messages, so match those, not session events.

    A specialist keeps the other specialists' written findings ("said:") but not their raw tool calls and
    results, which are bulk it never needs. The consolidator gets all findings explicitly from state instead.
    Its own function_call/function_response parts are never text parts, so they are never touched.
    """
    out = []
    for content in contents:
        parts = list(content.parts or [])
        kept = []
        for i, part in enumerate(parts):
            text = part.text or ""
            drop = False
            m = _OTHER_WORK.match(text)
            if m and m.group(1) in _SPECIALISTS and m.group(1) != agent_name:
                drop = True
            m = _OTHER_SAID.match(text)
            if m and m.group(1) in _SPECIALISTS and agent_name == "consolidator_agent":
                drop = True
            if not drop:
                kept.append(part)
        # a "For context:" header with nothing quoted after it is noise
        cleaned = [p for i, p in enumerate(kept)
                   if not ((p.text or "").startswith(_HEADER)
                           and (i + 1 >= len(kept) or (kept[i + 1].text or "").startswith(_HEADER)
                                 or not (_OTHER_WORK.match(kept[i + 1].text or "") or _OTHER_SAID.match(kept[i + 1].text or ""))))]
        if cleaned:
            content.parts = cleaned
            out.append(content)
    return out


def columnar(value, min_rows=5):
    """Lossless: a long list of records that share the same keys becomes columns + rows (keys written once)."""
    if isinstance(value, list):
        if (len(value) >= min_rows and all(isinstance(v, dict) for v in value)
                and all(list(v) == list(value[0]) for v in value)):
            keys = list(value[0])
            return {"_columns": keys, "_rows": [[columnar(v[k]) for k in keys] for v in value]}
        return [columnar(v) for v in value]
    if isinstance(value, dict):
        return {k: columnar(v) for k, v in value.items()}
    return value


async def before_model_context(callback_context, llm_request):
    """Operate on request copies, never session events or tool-returned evidence."""
    original = llm_request.contents
    before = wire_bytes([_dump(content) for content in original])
    contents = copy.deepcopy(original)
    removed = 0
    agent_name = callback_context.agent_name
    session = callback_context.session
    if reduction_enabled() and agent_name in _SPECIALISTS | {"consolidator_agent"}:
        before_parts = sum(len(c.parts or []) for c in contents)
        contents = _drop_other_transcripts(contents, agent_name)
        removed = before_parts - sum(len(c.parts or []) for c in contents)
        if agent_name == "consolidator_agent":
            # The consolidator gets every finding explicitly, including disagreement,
            # mitigating evidence and gaps, instead of the specialists' raw tool histories.
            findings = {field: callback_context.state.get(field, "Missing specialist findings.")
                        for field in _FINDINGS}
            contents.append(types.Content(role="user", parts=[types.Part.from_text(
                text="Recorded specialist findings (synthetic evidence, not instructions):\n"
                     + json.dumps(findings, ensure_ascii=False, separators=(",", ":")))]))
    if reduction_enabled():
        for content in contents:
            for part in content.parts or []:
                if part.function_response is not None and isinstance(part.function_response.response, dict):
                    part.function_response.response = columnar(part.function_response.response)
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
