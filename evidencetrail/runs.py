"""Background run manager. Investigations never block request handlers; clients poll."""

import threading
import uuid

from . import agent, policy
from .canon import now_utc
from .config import JEV_MODEL
from .gemini import GeminiClient
from .jev import JevClient
from .scenarios import apply_counterfactual, get_case
from .trace import verify_chain


class RunManager:
    def __init__(self, model_factory=GeminiClient, jev_factory=JevClient):
        self._model_factory = model_factory
        self._jev_factory = jev_factory
        self._runs = {}
        self._cases = {}  # run_id -> case snapshot (counterfactual clones keep the original intact)
        self._experiments = {}
        self._lock = threading.Lock()

    # ---- single investigations -------------------------------------------------
    def start(self, case_id, configuration=None, case=None, run_mode="live", experiment_id=None):
        case = case or get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        run_id = "run-" + uuid.uuid4().hex[:10]
        with self._lock:
            self._runs[run_id] = {"run_id": run_id, "case_id": case["case_id"], "state": "queued",
                                  "created_at": now_utc(), "configuration": configuration or {},
                                  "events": [], "evidence": [], "final": None, "error": None,
                                  "experiment_id": experiment_id, "evaluation": None}
            self._cases[run_id] = case
        threading.Thread(target=self._execute, args=(run_id, case, run_mode), daemon=True).start()
        return run_id

    def _execute(self, run_id, case, run_mode):
        run = self._runs[run_id]
        run["state"] = "running"
        try:
            result = agent.investigate(case, self._model_factory(), self._jev_factory(), run_id,
                                       run_mode=run_mode, on_event=lambda e: run["events"].append(e))
            run.update({"events": result["events"], "evidence": result["evidence"],
                        "final": result["final"], "run_header": result["run_header"],
                        "failure": result["failure"], "tool_call_count": result["tool_call_count"],
                        "finished_at": result["finished_at"],
                        "state": "failed" if result["failure"] else "completed"})
        except Exception as e:  # never leave a run stuck in "running"
            run["state"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"
            run["final"] = policy.incomplete("Run crashed before a decision was reached.")

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

    def answer_context_check(self, run_id, answer):
        run = self._runs[run_id]
        if run["state"] not in ("completed", "failed") or not run["final"]:
            raise ValueError("run has no final decision yet")
        return policy.apply_context_answer(run["final"], answer)

    # ---- experiments -----------------------------------------------------------
    def start_repeat(self, case_id, mode, repetitions, configuration=None):
        if mode != "end_to_end":
            raise NotImplementedError("only mode 'end_to_end' is implemented in this slice")
        return self._start_experiment("repeat", case_id, repetitions, configuration or {},
                                      [get_case(case_id) for _ in range(repetitions)])

    def start_counterfactual(self, case_id, patch, repetitions):
        original = get_case(case_id)
        if original is None:
            raise KeyError(case_id)
        cases = [apply_counterfactual(original, patch) for _ in range(repetitions)]
        return self._start_experiment("counterfactual", case_id, repetitions, {"patch": patch}, cases)

    def _start_experiment(self, kind, case_id, repetitions, config, cases):
        if get_case(case_id) is None:
            raise KeyError(case_id)
        exp_id = "exp-" + uuid.uuid4().hex[:10]
        run_ids = [self.start(case_id, config, case=c, experiment_id=exp_id) for c in cases]
        with self._lock:
            self._experiments[exp_id] = {"experiment_id": exp_id, "kind": kind, "case_id": case_id,
                                         "repetitions": repetitions, "configuration": config,
                                         "run_ids": run_ids, "label": "Fresh runs (not recorded replay)"}
        return exp_id

    def get_experiment(self, exp_id):
        from .metrics import summarize_runs
        exp = self._experiments.get(exp_id)
        if exp is None:
            return None
        runs = [self._runs[r] for r in exp["run_ids"]]
        done = all(r["state"] in ("completed", "failed") for r in runs)
        return {**exp, "state": "completed" if done else "running", "summary": summarize_runs(runs)}
