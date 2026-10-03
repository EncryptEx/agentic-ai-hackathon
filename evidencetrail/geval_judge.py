"""DeepEval custom judge adapter backed by the Gemini client.

Imported lazily: it needs deepeval installed. The judge is a model-based explanation
assessor, not independent ground truth.
"""

import json
import re

from deepeval.models import DeepEvalBaseLLM

from .gemini import GeminiClient
from .jev import ProviderUnavailable

JUDGE_SETTINGS = {"temperature": 0.0}


class GeminiJudge(DeepEvalBaseLLM):
    def __init__(self, client=None):
        self.client = client or GeminiClient(generation_settings=JUDGE_SETTINGS)
        self.returned_model_versions = set()
        self.calls = 0
        super().__init__(model=self.client.requested_model)

    def load_model(self):
        return self.client

    def get_model_name(self):
        return self.client.requested_model

    def supports_log_probs(self):
        return False

    def supports_structured_outputs(self):
        return False

    def _ask(self, prompt, schema):
        if schema is not None:
            prompt = (f"{prompt}\n\nRespond with ONLY one JSON object matching this JSON schema, "
                      f"no prose and no code fences:\n{json.dumps(schema.model_json_schema())}")
        turn = self.client.generate(None, [{"type": "user_input", "content": prompt}], [])
        self.calls += 1
        if turn.returned_model_version:
            self.returned_model_versions.add(turn.returned_model_version)
        if schema is None:
            return turn.text
        match = re.search(r"\{.*\}", turn.text, re.DOTALL)
        if not match:
            raise ProviderUnavailable("Judge returned no JSON object")
        try:
            return schema.model_validate_json(match.group(0))
        except ValueError as e:
            raise ProviderUnavailable(f"Judge JSON did not match schema: {type(e).__name__}") from None

    def generate(self, prompt, schema=None, *args, **kwargs):
        return self._ask(prompt, schema)

    async def a_generate(self, prompt, schema=None, *args, **kwargs):
        return self._ask(prompt, schema)

    def metadata(self):
        return {"judge_provider": "gemini", "judge_requested_model": self.client.requested_model,
                "judge_returned_model_versions": sorted(self.returned_model_versions),
                "judge_generation_settings": JUDGE_SETTINGS, "judge_calls": self.calls}
