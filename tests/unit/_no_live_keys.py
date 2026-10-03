"""Import this first in every EvidenceTrail test module.

evidencetrail.config loads a developer's gitignored .env, which may hold real provider keys. Unit
tests must never reach live APIs (cost, flakiness, leaking test data), so strip the keys after the
.env has been read. The live checks live in `python -m evidencetrail.live_check`, not in unit tests.
"""

import os

import evidencetrail.config  # noqa: F401  (loads .env once, so it cannot re-add keys later)

for _name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "TYPESAFE_API_KEY"):
    os.environ.pop(_name, None)
# Stripping once is not enough: DeepEval loads .env into the environment when it is imported. The kill switch
# makes the key getters return None no matter what the environment holds.
os.environ["EVIDENCETRAIL_DISABLE_LIVE"] = "1"
os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"
os.environ["EVIDENCETRAIL_ALERT_DB"] = ":memory:"
import tempfile
os.environ.setdefault("EVIDENCETRAIL_RECORD_DIR", tempfile.mkdtemp(prefix="et-records-"))
