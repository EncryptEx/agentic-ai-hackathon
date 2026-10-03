"""Runtime configuration. Provider keys are read from the server environment only."""

import os

PROMPT_VERSION = "investigator-prompt-v1"
POLICY_VERSION = "policy-v1-demo"
JEV_SPEC_VERSION = "jev-questions-v1"
SCENARIO_VERSION = "scenarios-v1"
RUBRIC_VERSION = "geval-rubric-v1"

GEMINI_MODEL = os.environ.get("EVIDENCETRAIL_GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
JEV_MODEL = os.environ.get("EVIDENCETRAIL_JEV_MODEL", "jev-latest")
JEV_URL = "https://api.typesafe.ai/v1/systemone"

MAX_TOOL_CALLS = 8
MAX_GRAPH_HOPS = 2
REQUEST_TIMEOUT_S = 60
RUN_TIMEOUT_S = 240

GENERATION_SETTINGS = {"temperature": 1.0}


def gemini_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def jev_key():
    return os.environ.get("TYPESAFE_API_KEY")
