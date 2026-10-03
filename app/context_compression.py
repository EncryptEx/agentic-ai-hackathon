"""Provider-independent, fail-open context compaction for synthetic investigations.

Only narrative leaves are eligible. Structured facts, schemas, system instructions,
call IDs and signatures never go through the compressor. Original evidence stays
in the database/session; callers work on deep copies of model-facing requests.
"""

import copy
import hashlib
import json
import os
import re
import time
import urllib.request
from collections import Counter, OrderedDict

CONDENSE_URL = "https://api.condense.chat/v1/compress"
NARRATIVE_FIELDS = frozenset({"summary", "description", "text"})
_CAUTION = re.compile(
    r"\b(no|not|never|without|missing|unknown|uncertain|unverified|incomplete|"
    r"contradict\w*|mitigat\w*|however|but|may|might|could|untrusted|synthetic|human)\b",
    re.IGNORECASE,
)
_FACT = re.compile(r"\S*\d\S*|\b[A-Z][A-Za-z_-]*\b")


def reduction_enabled():
    return os.getenv("CONTEXT_REDUCTION_ENABLED", "1") == "1"


def wire_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def valid_compaction(original, compacted):
    """Reject invented words, lost numeric/name tokens, and lost caution sentences.

    These checks are conservative, not a semantic-equivalence guarantee. Quality
    still needs paired case evaluations before choosing an aggressive rate.
    """
    if not isinstance(compacted, str) or not compacted.strip() or len(compacted) >= len(original):
        return False
    words = iter(original.split())
    if not all(any(word == wanted for word in words) for wanted in compacted.split()):
        return False
    if Counter(_FACT.findall(original)) != Counter(_FACT.findall(compacted)):
        return False
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", original):
        if _CAUTION.search(sentence) and sentence.strip() not in compacted:
            return False
    return True


class ContextCompressor:
    """Bounded per-run cache. One failed API call opens the circuit for this run."""

    def __init__(self):
        self.cache = OrderedDict()
        self.failed = False

    def compress(self, texts):
        started = time.monotonic()
        stats = {"api_calls": 0, "cache_hits": 0, "accepted": 0, "rejected": 0,
                 "eligible": 0, "status": "disabled", "duration_ms": 0}
        output = list(texts)
        if os.getenv("CONDENSE_ENABLED", "0") != "1":
            return output, stats
        # Unit/evaluation fakes must never make incidental live calls.
        if os.getenv("EVIDENCETRAIL_DISABLE_LIVE") == "1":
            stats["status"] = "live_disabled"
            return output, stats
        key = os.getenv("CONDENSE_API_KEY")
        if not key:
            stats["status"] = "missing_key"
            return output, stats
        try:
            model = os.getenv("CONDENSE_MODEL", "helene-1")
            rate = float(os.getenv("CONDENSE_COMPRESSION_RATE", "0.6"))
            minimum = max(1, int(os.getenv("CONDENSE_MIN_CHARS", "1200")))
            timeout = min(30.0, max(0.1, float(os.getenv("CONDENSE_TIMEOUT_SECONDS", "8"))))
            if model not in {"helene-1", "adeline-1"} or not 0 <= rate <= 1:
                raise ValueError("invalid settings")
        except ValueError:
            stats["status"] = "invalid_config"
            return output, stats
        pending = OrderedDict()
        total_chars = 0
        for index, text in enumerate(texts):
            if len(text) < minimum or len(text) > 100_000:
                continue
            stats["eligible"] += 1
            digest = hashlib.sha256(json.dumps([model, rate, text]).encode()).hexdigest()
            if digest in self.cache:
                self.cache.move_to_end(digest)
                output[index] = self.cache[digest]
                stats["cache_hits"] += 1
            elif not self.failed and (digest in pending or total_chars + len(text) <= 100_000):
                if digest not in pending:
                    pending[digest] = {"text": text, "indices": []}
                    total_chars += len(text)
                pending[digest]["indices"].append(index)
        stats["status"] = "circuit_open" if self.failed else "skipped"
        if pending:
            body = {"model": model, "messages": [
                {"role": "user", "content": item["text"]} for item in pending.values()]}
            if model == "helene-1":
                body["compression_rate"] = rate
            try:
                stats["api_calls"] = 1
                request = urllib.request.Request(
                    CONDENSE_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                    headers={"X-Condense-Auth-Token": key, "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise ValueError("oversized response")
                    messages = json.loads(raw)["messages"]
                if not isinstance(messages, list) or len(messages) != len(pending):
                    raise ValueError("invalid messages")
                if any(not isinstance(msg, dict) or msg.get("role") != "user"
                       or not isinstance(msg.get("content"), str) for msg in messages):
                    raise ValueError("invalid message")
                stats["status"] = "ok"
                for (digest, item), message in zip(pending.items(), messages):
                    candidate = message["content"]
                    accepted = valid_compaction(item["text"], candidate)
                    stats["accepted" if accepted else "rejected"] += 1
                    result = candidate if accepted else item["text"]
                    self.cache[digest] = result
                    for index in item["indices"]:
                        output[index] = result
                while len(self.cache) > 128:
                    self.cache.popitem(last=False)
            except Exception:  # Original context remains usable; never log secrets/error bodies.
                self.failed = True
                stats["status"] = "fallback"
        elif stats["cache_hits"]:
            stats["status"] = "cached"
        stats["duration_ms"] = int((time.monotonic() - started) * 1000)
        return output, stats

    def prepare(self, payloads):
        """Compact JSON whitespace and eligible narrative leaves on copied payloads."""
        copied = copy.deepcopy(payloads)
        locations = []

        def visit(value):
            if isinstance(value, dict):
                for field, child in value.items():
                    if field in NARRATIVE_FIELDS and isinstance(child, str):
                        locations.append((value, field, child))
                    elif isinstance(child, (dict, list)):
                        visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(copied)
        compressed, stats = self.compress([item[2] for item in locations])
        for (parent, field, _), text in zip(locations, compressed):
            parent[field] = text
        return copied, stats


def prepare_interactions(steps, compressor):
    """Preserve the native Interactions envelope and latest exchange exactly."""
    before = wire_bytes(steps)
    if not reduction_enabled() and os.getenv("CONDENSE_ENABLED", "0") != "1":
        return steps, {"status": "disabled", "before_bytes": before, "after_bytes": before}
    copied = copy.deepcopy(steps)
    locations, payloads = [], []
    # Only completed older results: latest results and function-call/signature steps stay exact.
    last_call = max((i for i, step in enumerate(steps) if step.get("type") == "function_call"), default=0)
    for step in copied[:last_call]:
        if step.get("type") != "function_result":
            continue
        for part in step.get("result", []):
            if part.get("type") != "text" or not isinstance(part.get("text"), str):
                continue
            try:
                payload = json.loads(part["text"])
            except ValueError:
                continue
            if isinstance(payload, (dict, list)):
                locations.append(part)
                payloads.append(payload)
    prepared, stats = compressor.prepare(payloads)
    for part, payload in zip(locations, prepared):
        part["text"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    stats.update(before_bytes=before, after_bytes=wire_bytes(copied))
    return copied, stats
