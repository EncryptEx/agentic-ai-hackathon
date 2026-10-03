"""Complete saved record of every investigation.

The working screen shows plain language; this is the full, redacted record behind it (every trace event with
exact request/response snapshots, all evidence payloads and hashes, the policy decision, the evaluation) kept
on the server for a technically competent person to check later. A saved record can be viewed and exported
after a server restart; it is a stored log, not an immutable or compliance-certified record.

Files live in data/investigations/ (override with EVIDENCETRAIL_RECORD_DIR) and are never committed.
"""

import json
import os
import re

from .canon import now_utc, redact

DEFAULT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "investigations"))
_ID = re.compile(r"^run-[0-9a-f]{10}$")
RECORD_VERSION = 1
_KEEP = ("run_id", "case_id", "state", "created_at", "finished_at", "elapsed_ms", "configuration", "run_header",
         "events", "evidence", "final", "failure", "error", "alert", "alert_error", "evaluation", "architecture",
         "tool_call_count", "consultation_count", "arm")


def record_dir():
    return os.environ.get("EVIDENCETRAIL_RECORD_DIR") or DEFAULT_DIR


def save_record(run, case):
    """Write (or refresh) the record for a run. Returns the path. Raises OSError if the disk refuses."""
    body = redact({
        "record_version": RECORD_VERSION, "saved_at": now_utc(),
        "notice": "Stored log of a synthetic investigation; not immutable and not compliance certified.",
        "run": {k: run.get(k) for k in _KEEP},
        "case": {k: (case or {}).get(k) for k in ("case_id", "name", "source", "synthetic", "transaction")},
    })
    os.makedirs(record_dir(), exist_ok=True)
    path = os.path.join(record_dir(), run["run_id"] + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=1)
    os.replace(tmp, path)  # never leave a half-written record
    return path


def load_record(run_id):
    if not isinstance(run_id, str) or not _ID.match(run_id):
        return None
    try:
        with open(os.path.join(record_dir(), run_id + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
