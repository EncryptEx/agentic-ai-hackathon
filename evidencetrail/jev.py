"""TypeSafe Jev client and versioned question specifications.

Jev is a judgment tool, not an agent. Raw typed results are kept exactly as returned;
no confidence is invented for fields whose schema lacks it.
"""

import json
import urllib.error
import urllib.request

from .canon import canonical
from .config import JEV_MODEL, JEV_URL, REQUEST_TIMEOUT_S, jev_key


class ProviderUnavailable(Exception):
    """Credentials missing or provider call failed; must stay visible, never fabricated."""


JEV_QUESTIONS = {
    "recipient_risk": {
        "type": "choice",
        "instructions": "Assess the recipient and network risk indicators supported by the supplied evidence.",
        "criteria": {
            "LOW": "No supported elevated recipient or network indicators.",
            "ELEVATED": "Supported anomalies exist but connection evidence is incomplete.",
            "HIGH": "Multiple supported recipient and network risk indicators.",
            "UNKNOWN": "Material evidence is missing.",
        },
    },
    "evidence_sufficiency": {
        "type": "choice",
        "instructions": ("Assess whether the available facts justify a policy recommendation, "
                         "not whether fraud is conclusively proven."),
        "criteria": {
            "SUFFICIENT_FOR_RECOMMENDATION": "Available facts justify a policy recommendation.",
            "NEED_MORE_EVIDENCE": "Material gaps remain before a recommendation is justified.",
        },
    },
    "next_step": {
        "type": "choice",
        "instructions": "Choose the most useful next step given checks already completed and remaining material gaps.",
        "criteria": {
            "CHECK_BEHAVIOR": "Behavior profile has not been checked and is materially needed.",
            "CHECK_DEVICE": "Device and session have not been checked and are materially needed.",
            "CHECK_RECIPIENT": "Recipient has not been checked and is materially needed.",
            "CHECK_GRAPH": "Recipient relationships have not been checked and are materially needed.",
            "FINISH": "All materially relevant checks are complete.",
        },
    },
    "manipulation_indicators": {
        "type": "noul",
        "instructions": ("The supplied evidence contains indicators consistent with manipulated-payer "
                         "fraud. This does not claim certainty about the payer's intent."),
    },
}


def build_state(items) -> str:
    """Serialize recorded evidence as the Jev state. Contains no case label or expected action."""
    return "\n".join(
        f"[{e['evidence_id']}] type={e['type']} source={e['source']} payload={canonical(e['payload'])}"
        for e in items)


def normalize(answers) -> dict:
    out = {}
    for key, a in answers.items():
        if a.get("type") == "choice":
            out[key] = a.get("choice")
        elif a.get("type") == "noul":
            out[key] = a.get("noul")
        elif a.get("type") == "score":
            out[key] = a.get("score")
    return out


class JevClient:
    def available(self):
        return bool(jev_key())

    def assess(self, state: str) -> dict:
        key = jev_key()
        if not key:
            raise ProviderUnavailable("TYPESAFE_API_KEY is not configured")
        body = {"state": state, "model": JEV_MODEL, "questions": JEV_QUESTIONS}
        req = urllib.request.Request(
            JEV_URL, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable(f"Jev HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise ProviderUnavailable(f"Jev request failed: {type(e).__name__}") from None
        answers = raw.get("answers")
        if not isinstance(answers, dict):
            raise ProviderUnavailable("Jev response had no 'answers' object")
        return {"raw": raw, "normalized": normalize(answers),
                "model": raw.get("model"), "usage": raw.get("usage")}
