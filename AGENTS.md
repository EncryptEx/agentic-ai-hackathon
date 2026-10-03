# Financial Crime Investigator — Coding Agent Guide

## Project Overview

This repository implements an AI Financial Crime Investigation system using Google ADK (Agent Development Kit). The system investigates synthetic banking customers, evaluates transactions and ownership structures, flags suspicious activities (e.g. structuring, smurfing, money mule flows, PEP exposure), and generates consolidated reports for human compliance officers.

### Target Multi-Agent Architecture

```
investigation_agent (Root Orchestrator)
├── investigation_pipeline (SequentialAgent)
│   ├── customer_agent      (Tools: list_customers, get_customer_profile, get_expected_activity, get_kyc_dossier, get_digital_telemetry)
│   ├── transaction_agent   (Tools: get_transactions, analyze_transactions, get_expected_activity, get_transaction_alerts)
│   ├── fraud_agent         (Tools: get_fraud_alerts, get_digital_telemetry, get_transactions, get_customer_profile)
│   ├── ownership_agent     (Tools: get_ownership_structure, get_country_risk)
│   └── risk_agent          (Tools: get_risk_assessment, get_customer_profile, get_country_risk, get_ownership_structure)
└── consolidator_agent     (Synthesizes specialist findings into 11-section report with Case Overview & Action Checklist)
```

### Critical Domain Guardrails

1. **Synthetic Data Only**: All entities, accounts, and transactions reside in SQLite database `data/fin_crime.db` or `data/kyc_aml.db` (100% fictional). Never state or imply real-world entities.
2. **Human in the Loop**: The system provides decision-support evidence and analysis. It must **never** make autonomous legal, SAR-filing, or regulatory decisions.
3. **No Hallucination**: Report only facts returned by the tools; do not fabricate transactions, counterparties, or ownership links.

---

## Development Phases

### Phase 1: Understand Requirements
Before writing any code, understand the project's requirements, constraints, and success criteria.

### Phase 2: Build and Implement
Implement agent logic in `app/`. Use `agents-cli playground` for interactive testing. Iterate based on user feedback.

### Phase 3: The Evaluation Loop (Main Iteration Phase)
Start with 1-2 eval cases, run `agents-cli eval run`, iterate by making changes and rerunning it until satisfied. Expect 5-10+ iterations. Once you have a baseline, reach for `agents-cli eval compare` (regression diffs), `agents-cli eval analyze` (cluster failure modes), and `agents-cli eval optimize` (auto-tune prompts). See the **Evaluation Guide** for metrics, dataset schema, LLM-as-judge config, and common gotchas.

### Phase 4: Pre-Deployment Tests
Run `uv run pytest tests/unit tests/integration`. Fix issues until all tests pass.

### Phase 5: Deploy to Dev
**Requires explicit human approval.** Run `agents-cli deploy` only after user confirms. See the **Deployment Guide** for details.

### Phase 6: Production Deployment
Ask the user: Option A (simple single-project) or Option B (full CI/CD pipeline with `agents-cli infra cicd`).

## Development Commands

| Command | Purpose |
|---------|---------|
| `agents-cli playground` | Interactive local testing |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests |
| `agents-cli eval dataset synthesize` | Synthesize multi-turn eval scenarios for your agent |
| `agents-cli eval run` | Run the agent over the eval dataset and grade the traces |
| `agents-cli eval generate` / `agents-cli eval grade` | Decoupled form: produce traces, then grade them |
| `agents-cli eval compare` | Compare two grade-results files (regression check) |
| `agents-cli eval analyze` | Cluster failure modes from grade results |
| `agents-cli eval metric list` | List built-in metrics available in the SDK |
| `agents-cli eval optimize` | Auto-tune agent prompts using eval data |
| `agents-cli lint` | Check code quality |
| `agents-cli infra single-project` | Set up project infrastructure (Terraform) |
| `agents-cli deploy` | Deploy to dev |
| `agents-cli scaffold enhance` | Add deployment target or CI/CD to project |
| `agents-cli scaffold upgrade` | Upgrade project to latest version |

---

## Operational Guidelines for Coding Agents

- **Code preservation**: Only modify code directly targeted by the user's request. Preserve all surrounding code, config values (e.g., `model`), comments, and formatting.
- **NEVER change the model** unless explicitly asked.
- **Model 404 errors**: Fix `GOOGLE_CLOUD_LOCATION` (e.g., `global` instead of `us-east1`), not the model name.
- **ADK tool imports**: Import the tool instance, not the module: `from google.adk.tools.load_web_page import load_web_page`
- **Run Python with `uv`**: `uv run python script.py`. Run `agents-cli install` first.
- **Stop on repeated errors**: If the same error appears 3+ times, fix the root cause instead of retrying.
- **Terraform conflicts** (Error 409): Use `terraform import` instead of retrying creation.
