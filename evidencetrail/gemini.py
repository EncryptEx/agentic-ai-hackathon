"""Gemini client (Interactions API, stateless: full history is sent every turn).

Wire format follows the current function-calling docs and must be re-verified against a
live call when credentials are available. Everything provider-specific is isolated here.
"""

import json
import urllib.error
import urllib.request

from .config import GEMINI_BASE_URL, GEMINI_MODEL, GENERATION_SETTINGS, REQUEST_TIMEOUT_S, gemini_key
from .jev import ProviderUnavailable


class ModelTurn:
    def __init__(self, steps, calls, text, returned_model_version=None, usage=None):
        self.steps = steps  # model steps to echo back in the next request
        self.calls = calls  # [{"id", "name", "arguments"}]
        self.text = text
        self.returned_model_version = returned_model_version
        self.usage = usage


class GeminiClient:
    provider = "gemini"

    def __init__(self, model=None):
        self.requested_model = model or GEMINI_MODEL
        self.generation_settings = dict(GENERATION_SETTINGS)

    def available(self):
        return bool(gemini_key())

    def generate(self, system_prompt, steps, tools) -> ModelTurn:
        key = gemini_key()
        if not key:
            raise ProviderUnavailable("GEMINI_API_KEY is not configured")
        body = {
            "model": self.requested_model,
            "system_instruction": system_prompt,
            "input": steps,
            "tools": tools,
            "store": False,  # stateless: no server-side answer reuse between runs
            "generation_config": dict(self.generation_settings),
        }
        req = urllib.request.Request(
            GEMINI_BASE_URL, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable(f"Gemini HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise ProviderUnavailable(f"Gemini request failed: {type(e).__name__}") from None
        out_steps = raw.get("steps")
        if not isinstance(out_steps, list):
            raise ProviderUnavailable("Gemini response had no 'steps' list")
        calls = [{"id": s.get("id"), "name": s.get("name"), "arguments": s.get("arguments", {})}
                 for s in out_steps if s.get("type") == "function_call"]
        text = " ".join(part.get("text", "") for s in out_steps if s.get("type") == "model_output"
                        for part in (s.get("content") or []) if isinstance(part, dict))
        return ModelTurn(out_steps, calls, text, raw.get("model") or raw.get("model_version"),
                         raw.get("usage"))
