"""Runtime configuration. Provider keys come from the server environment or a gitignored .env file.

They are never sent to the browser, written to traces or committed.
"""

import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_env_file(path, environ=None):
    """Minimal .env reader: KEY=VALUE lines, optional quotes, # comments. Blank values are ignored and
    real environment variables always win. Returns the names it set (never the values)."""
    environ = os.environ if environ is None else environ
    names = []
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return names
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value and key not in environ:
            environ[key] = value
            names.append(key)
    return names


load_env_file(os.path.join(_ROOT, ".env"))

PROMPT_VERSION = "investigator-prompt-v1"
TEAM_PROMPT_VERSION = "investigator-team-prompt-v1"
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
MAX_CONSULTATIONS = 6        # orchestrator -> specialist requests per run
SPECIALIST_MAX_TURNS = 5      # model turns a specialist may use per consultation
REQUEST_TIMEOUT_S = 60
RUN_TIMEOUT_S = 240

GENERATION_SETTINGS = {"temperature": 1.0}


def gemini_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def jev_key():
    return os.environ.get("TYPESAFE_API_KEY")
