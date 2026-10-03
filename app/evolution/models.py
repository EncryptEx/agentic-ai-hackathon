"""Self-Evolving Agent Loop Data Models and Contracts.
Defines schemas for Reflexion Insights, Policy Mutations, Shadow Backtesting, and Governance Proposals.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import datetime
import uuid


class FailureMode(str, Enum):
    MISCLASSIFIED_VICTIM_AS_MULE = "MISCLASSIFIED_VICTIM_AS_MULE"
    FALSE_POSITIVE_OFFSHORE_COMMERCE = "FALSE_POSITIVE_OFFSHORE_COMMERCE"
    UNIDENTIFIED_ATO_SESSION = "UNIDENTIFIED_ATO_SESSION"
    FRIENDLY_FRAUD_ESCALATION = "FRIENDLY_FRAUD_ESCALATION"
    INCOMPLETE_CDD_STALL = "INCOMPLETE_CDD_STALL"


@dataclass
class ReflexionInsight:
    insight_id: str
    case_id: str
    failure_mode: FailureMode
    root_cause_diagnosis: str
    flawed_rule_id: str
    overlooked_signals: List[str]
    corrective_guidance: str
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "case_id": self.case_id,
            "failure_mode": self.failure_mode.value,
            "root_cause_diagnosis": self.root_cause_diagnosis,
            "flawed_rule_id": self.flawed_rule_id,
            "overlooked_signals": self.overlooked_signals,
            "corrective_guidance": self.corrective_guidance,
            "created_at": self.created_at,
        }


@dataclass
class PolicyMutation:
    mutation_id: str
    target_rule_id: str
    version_tag: str
    previous_condition_dsl: str
    evolved_condition_dsl: str
    parameter_adjustments: Dict[str, Any]
    exemption_guards: List[str]
    mutation_rationale: str
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "target_rule_id": self.target_rule_id,
            "version_tag": self.version_tag,
            "previous_condition_dsl": self.previous_condition_dsl,
            "evolved_condition_dsl": self.evolved_condition_dsl,
            "parameter_adjustments": self.parameter_adjustments,
            "exemption_guards": self.exemption_guards,
            "mutation_rationale": self.mutation_rationale,
            "created_at": self.created_at,
        }


@dataclass
class BacktestMetricComparison:
    baseline_fp_rate_pct: float
    evolved_fp_rate_pct: float
    fp_reduction_pct: float
    baseline_fn_rate_pct: float
    evolved_fn_rate_pct: float
    decision_stability_rate: float
    benchmark_dataset_size: int
    validation_status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_fp_rate_pct": self.baseline_fp_rate_pct,
            "evolved_fp_rate_pct": self.evolved_fp_rate_pct,
            "fp_reduction_pct": self.fp_reduction_pct,
            "baseline_fn_rate_pct": self.baseline_fn_rate_pct,
            "evolved_fn_rate_pct": self.evolved_fn_rate_pct,
            "decision_stability_rate": self.decision_stability_rate,
            "benchmark_dataset_size": self.benchmark_dataset_size,
            "validation_status": self.validation_status,
        }


@dataclass
class GovernanceProposal:
    proposal_id: str
    title: str
    status: str  # "READY_FOR_HUMAN_APPROVAL", "DEPLOYED", "REJECTED"
    reflexion: ReflexionInsight
    mutation: PolicyMutation
    backtest: BacktestMetricComparison
    compliance_impact_statement: str
    hot_deploy_available: bool = True
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "status": self.status,
            "reflexion": self.reflexion.to_dict(),
            "mutation": self.mutation.to_dict(),
            "backtest": self.backtest.to_dict(),
            "compliance_impact_statement": self.compliance_impact_statement,
            "hot_deploy_available": self.hot_deploy_available,
            "created_at": self.created_at,
        }
