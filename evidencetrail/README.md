# EvidenceTrail

Investigates suspicious synthetic transfers with a team of agents, supports the investigation with Jev
judgments, lets a deterministic policy decide the simulated action, and records an evidence-linked audit trail.
All data is synthetic. Nothing moves or blocks real money.

## How it works

- **Agent team** (`team.py`): an orchestrator that can only consult three specialists
  (`behavior_device`, `recipient_network`, `risk_judge`). Every tool result lands in one evidence store with a
  stable ID. Jev is a tool used by the risk judge, not an agent.
- **Policy** (`policy.py`): deterministic and authoritative. The agent's recommendation is recorded and a
  disagreement is flagged, but it never changes the action (set `EVIDENCETRAIL_AGENT_ESCALATION=1` to let a more
  cautious agent raise it).
- **Alerts** (`alerts.py`): Jev triages each finished investigation. An alert is raised when Jev finds it
  suspicious or the policy routes it away from Allow; Jev can raise an alert but never suppress a policy one.
  A flagged customer can be handed to the ADK specialist team (combined server only).
- **Data**: five hand-built scenarios, or real transactions from the FRAML data seed (`seed.py`). Seed evidence is
  time-causal and the generator's answer key is hidden from the agents (`seed_labels.py` is evaluator-only).
- **Explanation quality**: the three official DeepEval G-Eval metrics, run after the decision.

## Run it

```bash
python cli.py serve            # dashboard at http://localhost:8000/dashboard  ->  "Investigator" tab
```

Keys go in a gitignored `.env` (see `.env.example`): `GEMINI_API_KEY` (Google AI Studio) and `TYPESAFE_API_KEY`.

## Check that the live providers work

```bash
python -m evidencetrail.live_check          # wire formats against the real Gemini and Jev APIs
python -m evidencetrail.live_check --e2e    # plus all five scenarios and the real G-Eval judge
```

## Decision-consistency report (demo once, then periodically)

Consistency is a recorded report, not something to run from the UI. It runs the real agent team and Jev several
times per scenario, repeats the decision on frozen evidence, and checks that the action follows the evidence.

```bash
python -m evidencetrail.consistency                 # 5 fresh runs per scenario
python -m evidencetrail.consistency --ablation      # also: rules vs team without Jev vs team with Jev
python -m evidencetrail.consistency --repetitions 10 --scenario case-manipulated
```

Reports are saved to `data/consistency/` (gitignored; override with `EVIDENCETRAIL_REPORT_DIR`) and shown
read-only in the Investigator tab. The command exits `0` when every scenario was consistent with no failed runs and
`2` otherwise, so a scheduler can alert on it. If the company wants a periodic check, for example monthly:

```bash
# Linux/macOS cron: 06:00 on the 1st of each month
0 6 1 * * cd /path/to/repo && python -m evidencetrail.consistency || echo "EvidenceTrail consistency check needs attention"

# Windows Task Scheduler
schtasks /Create /SC MONTHLY /D 1 /ST 06:00 /TN EvidenceTrailConsistency /TR "cmd /c cd /d C:\path\to\repo && python -m evidencetrail.consistency"
```

Consistency is not correctness. Runs can agree and still be wrong, and five synthetic cases say nothing about fraud
precision, recall or calibration.

## Tests

```bash
python -m pytest tests/unit          # no network, no keys: a kill switch hides provider keys from unit tests
```
