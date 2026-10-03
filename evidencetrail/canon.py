"""Canonical serialization, hashing and redaction helpers."""

import copy
import hashlib
import json
from datetime import datetime, timezone

_SENSITIVE = ("authorization", "api_key", "api-key", "x-goog-api-key", "bearer")


def canonical(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(data) -> str:
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def redact(data):
    """Return a deep copy with credential-looking keys masked."""
    data = copy.deepcopy(data)

    def walk(node):
        if isinstance(node, dict):
            for k in list(node):
                if any(s in str(k).lower() for s in _SENSITIVE):
                    node[k] = "[REDACTED]"
                else:
                    walk(node[k])
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return data
