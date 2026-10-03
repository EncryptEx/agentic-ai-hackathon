"""Gemini client (Interactions API, stateless: full history is sent every turn).

Wire format follows the current function-calling docs and must be re-verified against a
live call when credentials are available. Everything provider-specific is isolated here.
"""

import json
import urllib.error
import urllib.request

from app.context_compression import ContextCompressor, prepare_interactions

from .config import GEMINI_BASE_URL, GEMINI_MODEL, GENERATION_SETTINGS, REQUEST_TIMEOUT_S, gemini_key
from .jev import ProviderUnavailable, post_json_with_retry


class ModelTurn:
    def __init__(self, steps, calls, text, returned_model_version=None, usage=None):
        self.steps = steps  # model steps to echo back in the next request
        self.calls = calls  # [{"id", "name", "arguments"}]
        self.text = text
        self.returned_model_version = returned_model_version
        self.usage = usage


class GeminiClient:
    provider = "gemini"

    def __init__(self, model=None, generation_settings=None):
        self.requested_model = model or GEMINI_MODEL
        self.generation_settings = dict(generation_settings or GENERATION_SETTINGS)
        self._compressor = ContextCompressor()
        self._context_scope = None

    def available(self):
        return bool(gemini_key())

    def generate(self, system_prompt, steps, tools) -> ModelTurn:
        key = gemini_key()
        if not key:
            raise ProviderUnavailable("GEMINI_API_KEY is not configured")
        # A client can be reused by evaluations; never reuse a case's cache in another case.
        scope = json.dumps(steps[0] if steps else None, sort_keys=True)
        if scope != self._context_scope:
            self._compressor = ContextCompressor()
            self._context_scope = scope
        prepared_steps, context_stats = prepare_interactions(steps, self._compressor)
        body = {
            "model": self.requested_model,
            "input": prepared_steps,
            "store": False,  # stateless: no server-side answer reuse between runs
            "generation_config": dict(self.generation_settings),
        }
        if system_prompt:
            body["system_instruction"] = system_prompt
        if tools:
            body["tools"] = tools
        raw = post_json_with_retry(
            lambda: urllib.request.Request(
                GEMINI_BASE_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"}), key, "Gemini")
        out_steps = raw.get("steps")
        if not isinstance(out_steps, list):
            raise ProviderUnavailable("Gemini response had no 'steps' list")
        calls = [{"id": s.get("id"), "name": s.get("name"), "arguments": s.get("arguments", {})}
                 for s in out_steps if s.get("type") == "function_call"]
        text = _extract_text(out_steps)
        turn = ModelTurn(out_steps, calls, text, raw.get("model") or raw.get("model_version"),
                         raw.get("usage"))
        turn.request_steps = prepared_steps
        turn.context_stats = context_stats
        return turn


def _extract_text(steps) -> str:
    """Collect text from non-call steps. The text step type name is not pinned down by the docs
    we verified, so accept any step that is not a function call or user input."""
    parts = []
    for s in steps:
        if s.get("type") in ("function_call", "user_input", "function_result"):
            continue
        content = s.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(p.get("text", "") for p in content if isinstance(p, dict))
        elif isinstance(s.get("text"), str):
            parts.append(s["text"])
    return " ".join(p for p in parts if p).strip()
