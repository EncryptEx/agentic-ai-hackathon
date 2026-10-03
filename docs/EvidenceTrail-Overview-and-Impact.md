# EvidenceTrail: what it is, what it does for a bank, and what it costs

All data is synthetic. Numbers marked **measured** come from runs in this repository (files in `data/impact/`);
numbers marked **assumption** are placeholders you must replace with your own prices and staffing costs.

## 1. The one-paragraph version

A compliance analyst who gets a suspicious-transaction alert today opens five or six systems, copies facts into a
document, and writes up a case file by hand. EvidenceTrail replaces that legwork with a **team of AI agents**:
specialists that each investigate one angle (customer and KYC, transactions, fraud telemetry, ownership, risk), query
the bank's own tools, and hand a consolidated, evidence-cited case file to the human. The human still decides. Every
claim points to a stored piece of evidence, every step is recorded in a tamper-evident trace, and a deterministic
policy, not the model, sets the simulated outcome. Jev (a risk model) and G-Eval (an explanation checker) support the
agents; they are not the product.

## 2. What today's tools usually do not do

Typical transaction-monitoring and fraud-rule systems are good at one thing: raising an alert when a rule fires.
They usually stop there. Gaps this project targets:

| Gap in a typical setup | What EvidenceTrail does instead |
|---|---|
| An alert says *that* a rule fired, not *why it matters* | Agents gather the context around it and write the reasoning down |
| Facts live in separate systems (profile, KYC, transactions, device, ownership) | Specialist agents each pull their slice with registered tools and share one evidence store |
| The analyst re-types facts into a case file | A consolidated case file is drafted automatically, with evidence IDs on every claim |
| Missing data is invisible | Missing, failed or contradictory evidence is reported as missing, never as reassuring |
| "The AI said so" is not auditable | Every tool call, result, and decision is hash-chained in a trace and saved as a record |
| A model alone could decide anything | Deterministic policy v1 is authoritative; the model can recommend, escalate or disagree, never override |
| Hard to see whether the AI is consistent | A recorded consistency report and a G-Eval quality check on every explanation |

Nothing here replaces the analyst. It removes the gathering and drafting, and leaves judgement with the person.

## 3. How the agents work (the main attraction)

**Two agent teams, same idea.**

- **EvidenceTrail team** (alert triage on a single transfer): an orchestrator plus three specialists
  (behaviour and device, recipient and network, risk judge). The orchestrator decides whom to consult; specialists call
  registered tools; every result gets a stable ID (EV-001, EV-002, ...) in a shared evidence store.
- **ADK investigation suite** (full customer case file): five specialists (customer/KYC, transactions, fraud and
  cybercrime, ownership, risk) and a consolidator that writes an 11-section case file: overview, observations, AML and
  fraud findings, ownership, risk score, evidence per finding, **contradictory or mitigating evidence, missing
  information, and suggested next questions**.

**Why a team and not one agent.** Each specialist has a narrow job, a small tool set and its own context, so it can
be checked, replaced or audited on its own. One generalist prompt that sees every tool result at once is slower,
more expensive and harder to audit.

**Guardrails that make agents usable in a bank.**

1. Evidence IDs on every claim; invalid references are flagged.
2. Policy v1 decides the simulated action; agent disagreement is recorded, not hidden.
3. Customer-supplied text is treated as untrusted; synthetic-data labels are never shown to agents.
4. A hash-chained trace and a saved record per investigation let a reviewer replay what happened.
5. Time-causal data: an agent only ever sees what was knowable before the transaction.

## 4. How it makes the analyst's job easier

| Analyst task today | With the agents |
|---|---|
| Open profile, KYC, transactions, device, ownership screens | Done by specialists in parallel, in about 20-30 s (triage) or about 100 s (full case file), **measured** |
| Write up findings and cite sources | Case file drafted with evidence IDs and an explicit "missing information" section |
| Decide what to ask next | "Suggested next investigative questions" section |
| Explain a decision to audit | Trace + record + plain-language reasoning, reproducible from the saved evidence |
| Judge whether the tool is trustworthy | Consistency report and G-Eval scores on each explanation |

## 5. Measured results

### 5.1 The study

48 labelled synthetic transactions (24 the data generator marked as attacks, 24 clean), each run three ways:
rules only, agent team without Jev, full system with Jev. The generator's labels are used only to score results; the
agents never see them. `data/impact/impact-20261003-165251.json` has every row.

| Arm | Attacks caught | Clean wrongly flagged | Attack value missed (USD) |
|---|---|---|---|
| Rules only (policy v1, no model) | 18 / 24 (75%) | 8 / 24 (33%) | 93,984 of 221,031 |
| Agent team, no Jev | 18 / 24 (75%) | 8 / 24 (33%) | 93,984 |
| Full system (agents + Jev) | 18 / 24 (75%) by policy; **23 / 24 (96%)** counting Jev alerts | 8 / 24 by policy; **14 / 24 (58%)** counting Jev alerts | 93,984 by policy; **0.89** counting Jev alerts |

95% intervals are wide (for example 55-88% for 18 of 24). Treat these as a sample, not a rate.

### 5.2 What this says about the agents, honestly

- **The agents' final decision matched the rules baseline in 48 of 48 cases.** That is by design: the deterministic
  policy is authoritative over the same evidence the agents gather. So this study does **not** show that agents
  catch more attacks than rules. Do not claim that.
- The agents' value is in **how the case gets built**, which this study does not score: gathering across systems,
  writing the explanation, reporting missing evidence, and producing an auditable trail. Section 6 prices that.
- To make that value measurable, the next experiments should score the case file itself: completeness against a
  checklist of required findings, time to produce it, and how many tool failures it handles gracefully.

### 5.3 Jev (supporting role)

- Jev raised detection from 18 to 23 of 24 attacks and cut missed attack value from 93,984 to 0.89 USD in this sample.
- It also raised false alerts from 8 to 14 of 24 clean transactions, 6 of them Jev-only.
- It roughly doubled model usage per case (input tokens 348k to 680k across the 48 runs).
- Reading: Jev is a recall booster that adds review work. Whether that trade is worth it depends on the cost of a
  missed attack versus a wasted review.

### 5.4 G-Eval (supporting role)

- Average scores were 0.96-0.98 (grounding 0.977, completeness 0.973, relevance 0.963); 47-48 of 48 passed each metric.
- As a gate for wrong decisions it was **not useful**: it held 1 of 14 wrong decisions and 0 of 34 right ones. G-Eval
  judges the quality of explanations; it does not know whether the decision was correct.
- Reading: keep G-Eval as an explanation-quality monitor and audit signal, not as a correctness filter.

### 5.5 Condense and context size (supporting role)

- The standalone Condense compress API could not be measured: the account returned HTTP 402 (no credit balance).
  The integration is built, tested with a fake provider, switched off by default and fails open.
- What was measured instead is our own context cleanup on the full ADK case file, on three customers, comparing the
  code before and after. Earlier code was not actually isolating specialist context (ADK replays other agents as plain
  text); that was fixed in this work.

| Customer | Prompt tokens before | After | Change |
|---|---|---|---|
| CUST-00060 | 600,051 | 95,072 | -84% |
| CUST-00036 | 483,112 | 154,787 | -68% |
| CUST-00085 | 301,888 | 130,338 | -57% |
| Total | 1,385,051 | 380,197 | **-72.5%** |

Caveats: three customers, one run each; output tokens did not fall; the reports cited somewhat different sets of
transaction IDs (before/after IDs in common: 23 of 35/25, 27 of 34/27, 23 of 26/33), so quality equivalence is **not**
proven. A paired quality check with repeated runs is the next step before claiming it as a pure saving.

## 6. What it costs, and what it saves

Prices below are **assumptions** (Gemini 0.30 USD per million input tokens and 2.50 per million output tokens;
analyst 45 USD per hour; 25 minutes to review one alert by hand; 60 minutes to assemble a case file by hand).
Replace them in `evidencetrail/impact.py` or via `EVIDENCETRAIL_ASSUMPTIONS`.

| Item | Per unit | Basis |
|---|---|---|
| Agent triage of one transfer, no Jev | about 0.012 USD, about 22 s | measured tokens x assumed price |
| Agent triage plus Jev | about 0.018 USD, about 31 s | same (Jev call price assumed 0, unknown) |
| Full ADK case file, before context cleanup | about 0.17 USD, about 85 s | measured tokens, thinking tokens not included |
| Full ADK case file, after context cleanup | about 0.07 USD, about 95 s | same |
| Analyst reviewing one alert by hand | about 18.75 USD | assumption |
| Analyst assembling one case file by hand | about 45 USD | assumption |

What to take from it:

1. **Model cost is small next to analyst time.** A case file costs cents; an hour of analyst time costs dollars
   per minute. The money story is analyst time and risk, not tokens.
2. **Agents did not save review time in this study**, because the decisions match the rules, so the same alerts get
   reviewed. Any saving from agents is in drafting the case file and gathering evidence, not in fewer alerts.
3. **Jev trades more false alerts for more attacks caught.** In this sample that is 6 more wasted reviews
   (about 112 USD at the assumed review cost) against about 94,000 USD of attack value no longer missed.
4. **Context cleanup cut the model cost of a case file by about 60%** (input tokens fell 72.5%, output unchanged),
   subject to the quality caveat above.

Scaling these to a portfolio is not valid from this sample: it is enriched with attacks (74 of 106 candidate
transactions are flagged), so real-world alert volumes and rates will differ.

## 7. How to present it

- Lead with the **workflow**: alert in, evidence-cited case file out, human decides, everything auditable.
- Show **one live investigation**: the trace, the evidence IDs, the "missing information" section.
- Say plainly that **policy decides and agents explain**. That is a safety feature, and it is why the agents'
  decisions matched the rules.
- Use Jev as the **extra safety net** (more attacks caught, at a review cost) and G-Eval as the **quality monitor**.
- Report Condense honestly: built, safe, not measurable without API access; our own context cleanup is the real,
  measured token saving so far.

## 8. Limits to state up front

- Synthetic data only; the answer key is the generator's, not real-world truth.
- 48 transactions, one run per arm: wide intervals, no claim about real precision or recall.
- Agent decisions equal policy by construction; agent value is in the case file, which is not yet scored.
- Prices and analyst costs are placeholders.
- Jev's per-call price is unknown and counted as zero.
- Context cleanup quality is unverified on repeated runs.
