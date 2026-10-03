"""Background run manager. Investigations never block request handlers; clients poll."""

import threading
import time
import uuid

import sqlite3

from . import agent, evaluator, experiments, policy, team
from .alerts import AlertStore
from .canon import now_utc, redact
from .config import JEV_MODEL
from .evidence import EvidenceStore
from .gemini import GeminiClient
from .jev import JevClient
from .metrics import summarize_runs
from .scenarios import SCENARIOS, apply_counterfactual, get_case
from .trace import verify_chain

MAX_CONCURRENT_RUNS = 4  # be polite to providers when experiments launch many runs
_DONE = ("completed", "failed")


class RunManager:
    def __init__(self, model_factory=GeminiClient, jev_factory=JevClient, judge_factory=None,
                 run_mode="live", alert_store=None, architecture="team"):
        self._architecture = architecture  # "team" (orchestrator + specialists) or "single"
        self._run_mode = run_mode  # "live", or "development" when providers are stand-ins
        self._model_factory = model_factory
        self._jev_factory = jev_factory
        self._judge_factory = judge_factory
        self._runs = {}
        self._cases = {}  # run_id -> case snapshot (counterfactual clones keep the original intact)
        self._experiments = {}
        self._alerts = alert_store or AlertStore()
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT_RUNS)

    # ---- single investigations -------------------------------------------------
    def start(self, case_id, configuration=None, case=None, run_mode=None, experiment_id=None,
              arm="with_jev", alerts_enabled=True, architecture=None):
        run_mode = run_mode or self._run_mode
        architecture = architecture or (configuration or {}).get("architecture") or self._architecture
        if architecture not in ("team", "single"):
            raise ValueError("architecture must be 'team' or 'single'")
        case = case or get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        run_id = "run-" + uuid.uuid4().hex[:10]
        with self._lock:
            self._runs[run_id] = {"run_id": run_id, "case_id": case["case_id"], "state": "queued",
                                  "created_at": now_utc(), "configuration": configuration or {},
                                  "events": [], "evidence": [], "final": None, "error": None,
                                  "experiment_id": experiment_id, "evaluation": None, "arm": arm,
                                  "alert": None, "alert_error": None, "architecture": architecture}
            self._cases[run_id] = case
        threading.Thread(target=self._execute, args=(run_id, case, run_mode, arm, alerts_enabled, architecture), daemon=True).start()
        return run_id

    def _execute(self, run_id, case, run_mode, arm, alerts_enabled, architecture):
        run = self._runs[run_id]
        with self._slots:
            run["state"] = "running"
            started = time.monotonic()
            store = EvidenceStore()

            def on_event(event):  # stream events and evidence while the run is in progress
                run["events"].append(event)
                run["evidence"] = store.all()

            try:
                investigate = team.investigate_team if architecture == "team" else agent.investigate
                result = investigate(case, self._model_factory(), self._jev_factory(), run_id,
                                           run_mode=run_mode, on_event=on_event,
                                           enable_jev=(arm != "no_jev"), store=store,
                                           triage=alerts_enabled)
                self._persist_alert(run, result.get("alert"))  # before the state flips to completed
                run.update({"events": result["events"], "evidence": result["evidence"],
                            "final": result["final"], "run_header": result["run_header"],
                            "failure": result["failure"], "tool_call_count": result["tool_call_count"],
                            "consultation_count": result.get("consultation_count"),
                            "finished_at": result["finished_at"],
                            "state": "failed" if result["failure"] else "completed"})
            except Exception as e:  # never leave a run stuck in "running"
                run["state"] = "failed"
                run["error"] = f"{type(e).__name__}: {e}"
                run["final"] = policy.incomplete("Run crashed before a decision was reached.")
            run["elapsed_ms"] = int((time.monotonic() - started) * 1000)

    def _persist_alert(self, run, alert):
        if not alert:
            return
        try:
            run["alert"] = self._alerts.create(alert)
        except sqlite3.Error as e:  # the alert is still shown on the run, but we say it was not saved
            run["alert"], run["alert_error"] = alert, f"alert could not be saved: {e}"

    # ---- alerts ----------------------------------------------------------------
    def list_alerts(self, status=None, severity=None):
        return self._alerts.list(status=status, severity=severity)

    def get_alert(self, alert_id):
        return self._alerts.get(alert_id)

    def set_alert_status(self, alert_id, status, note=None):
        return self._alerts.set_status(alert_id, status, note)

    def get(self, run_id):
        run = self._runs.get(run_id)
        if run is None:
            return None
        view = dict(run)
        view["jev_model_requested"] = JEV_MODEL
        view["recorded_audit_trail_verified"] = verify_chain(run["events"]) if run["events"] else None
        return view

    def case_for(self, run_id):
        return self._cases.get(run_id)

    def export_run(self, run_id):
        """Redacted trace export. A stored log, not an immutable or compliance-certified record."""
        run = self._runs.get(run_id)
        if run is None:
            return None
        final = run.get("final") or {}
        return redact({
            "export_notice": "Recorded audit trail of a synthetic investigation; not immutable and not "
                             "compliance certified. Provider credentials are never included.",
            "run_id": run_id, "case_id": run["case_id"], "state": run["state"],
            "run_header": run.get("run_header"), "events": run["events"], "evidence": run["evidence"],
            "claims": final.get("claims"), "final": run.get("final"), "alert": run.get("alert"), "failure": run.get("failure"),
            "evaluation": run.get("evaluation"), "hash_chain_verified": verify_chain(run["events"]) if run["events"] else None})

    def start_evaluation(self, run_id, repeats=1):
        """Evaluate a finished run in the background; poll GET /api/investigations/{id}."""
        run = self._runs[run_id]
        if run["state"] not in _DONE:
            raise ValueError("run is still in progress")
        with self._lock:
            if run["evaluation"] and run["evaluation"].get("state") == "running":
                return run["evaluation"]
            run["evaluation"] = {"state": "running", "started_at": now_utc()}
        threading.Thread(target=self._evaluate, args=(run_id, repeats), daemon=True).start()
        return run["evaluation"]

    def _evaluate(self, run_id, repeats):
        run = self._runs[run_id]
        try:
            run["evaluation"] = evaluator.evaluate(run, self._cases[run_id], self._judge_factory, repeats=repeats)
        except Exception as e:
            run["evaluation"] = {"state": "failed", "error": f"{type(e).__name__}: {e}"}

    def answer_context_check(self, run_id, answer):
        run = self._runs[run_id]
        if run["state"] not in _DONE or not run["final"]:
            raise ValueError("run has no final decision yet")
        return policy.apply_context_answer(run["final"], answer)

    # ---- experiments -----------------------------------------------------------
    def start_repeat(self, case_id, mode, repetitions, configuration=None):
        if get_case(case_id) is None:
            raise KeyError(case_id)
        if mode == "fixed_evidence":
            return self._start_fixed_evidence(case_id, repetitions, configuration or {})
        if mode != "end_to_end":
            raise ValueError("mode must be 'end_to_end' or 'fixed_evidence'")
        return self._start_experiment("repeat", case_id, repetitions, configuration or {},
                                      [get_case(case_id) for _ in range(repetitions)])

    def start_counterfactual(self, case_id, patch, repetitions):
        original = get_case(case_id)
        if original is None:
            raise KeyError(case_id)
        cases = [apply_counterfactual(original, patch) for _ in range(repetitions)]
        return self._start_experiment("counterfactual", case_id, repetitions, {"patch": patch}, cases)

    def _register(self, record):
        exp_id = "exp-" + uuid.uuid4().hex[:10]
        record["experiment_id"] = exp_id
        with self._lock:
            self._experiments[exp_id] = record
        return exp_id

    def _start_experiment(self, kind, case_id, repetitions, config, cases):
        run_ids = [self.start(case_id, config, case=c, alerts_enabled=False) for c in cases]
        exp_id = self._register({"kind": kind, "case_id": case_id, "repetitions": repetitions,
                                 "configuration": config, "run_ids": run_ids,
                                 "label": "Fresh runs (not recorded replay)"})
        for r in run_ids:
            self._runs[r]["experiment_id"] = exp_id
        return exp_id

    def _start_fixed_evidence(self, case_id, repetitions, config):
        exp_id = self._register({"kind": "fixed_evidence", "case_id": case_id, "repetitions": repetitions,
                                 "configuration": config, "state": "running", "progress": 0,
                                 "result": None, "error": None,
                                 "label": "Fresh model calls on one frozen evidence bundle (not recorded replay)"})
        exp = self._experiments[exp_id]

        def work():
            try:
                with self._slots:
                    exp["result"] = experiments.fixed_evidence_experiment(
                        get_case(case_id), self._model_factory(), self._jev_factory(), repetitions,
                        on_progress=lambda n: exp.__setitem__("progress", n))
                exp["state"] = "completed"
            except Exception as e:
                exp["state"], exp["error"] = "failed", f"{type(e).__name__}: {e}"

        threading.Thread(target=work, daemon=True).start()
        return exp_id

    def start_ablation(self, case_ids, repetitions):
        case_ids = case_ids or list(SCENARIOS)
        if any(c not in SCENARIOS for c in case_ids):
            raise KeyError("unknown case")
        arms = {"no_jev": {}, "with_jev": {}}
        for arm in arms:
            for cid in case_ids:
                arms[arm][cid] = [self.start(cid, {"arm": arm}, arm=arm, alerts_enabled=False)
                                  for _ in range(repetitions)]
        rules = {cid: experiments.rules_baseline(get_case(cid)) for cid in case_ids}
        exp_id = self._register({"kind": "ablation", "case_ids": case_ids, "repetitions": repetitions,
                                 "configuration": {}, "arms": arms, "rules_results": rules,
                                 "label": "Fresh runs per arm; rules arm is deterministic"})
        for arm_runs in arms.values():
            for ids in arm_runs.values():
                for r in ids:
                    self._runs[r]["experiment_id"] = exp_id
        return exp_id

    def get_experiment(self, exp_id):
        exp = self._experiments.get(exp_id)
        if exp is None:
            return None
        kind = exp["kind"]
        if kind == "fixed_evidence":
            return dict(exp)
        if kind == "ablation":
            run_ids = [r for arm in exp["arms"].values() for ids in arm.values() for r in ids]
            done = all(self._runs[r]["state"] in _DONE for r in run_ids)
            public = {k: v for k, v in exp.items() if k not in ("rules_results", "arms")}
            return {**public, "state": "completed" if done else "running",
                    "summary": experiments.summarize_ablation(exp, self._runs, exp["rules_results"])}
        runs = [self._runs[r] for r in exp["run_ids"]]
        done = all(r["state"] in _DONE for r in runs)
        return {**exp, "state": "completed" if done else "running", "summary": summarize_runs(runs)}
