"""Local LLM-as-judge for `custom_response_quality` (see eval_config.yaml)."""

import os
import sys
import threading
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

# Safe env loading that works when executed via exec() without __file__
env_path = os.path.join(os.getcwd(), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
load_dotenv()

_local = threading.local()


class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str


def _client() -> genai.Client:
    """One client per grading thread."""
    client = getattr(_local, "client", None)
    if client is None:
        client = _local.client = genai.Client()
    return client


def evaluate(instance):
    reference = instance.get("reference")
    rubric = (
        "Grade the agent's financial crime investigation report on a 1-5 scale (1 poor, 5 excellent) for: "
        "1. Investigative accuracy and factual grounding in the tool outputs. "
        "2. Identification of financial crime typologies (e.g., structuring TM-01, money mule TM-02, ATO FR-01, PEP exposure). "
        "3. Completeness of the 11-section standardized compliance report. "
        "4. Inclusion of synthetic data and human-in-the-loop compliance officer disclaimers."
    )
    if reference:
        rubric += (
            " The response should align with the expected investigative findings below; penalize "
            "missed typologies, fabricated facts, or factual disagreements."
        )
    prompt = (
        f"You are an expert QA evaluator for an AI financial crime investigator. {rubric}\n"
        f"User Prompt: {instance.get('prompt', '')}\n"
        f"Final Response: {instance.get('response', '')}\n"
    )
    if reference:
        prompt += f"Expected Answer (ground truth): {reference}\n"
    if "agent_data" in instance:
        prompt += f"Full Agent Trace: {instance.get('agent_data', '')}\n"

    response = _client().models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,  # deterministic grading
            response_mime_type="application/json",
            response_schema=_Verdict,  # guaranteed schema-valid JSON
        ),
    )
    verdict = response.parsed
    if verdict is None:
        return {"score": 0, "explanation": response.text or ""}
    return {"score": max(1, min(5, verdict.score)), "explanation": verdict.explanation}
