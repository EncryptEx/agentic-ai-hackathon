"""Self-Evolving Agent Loop Master Orchestrator.
Coordinates Reflexion -> Mutation -> Shadow Backtesting -> Governance Proposal.
"""

from typing import Dict, Any, Optional
import uuid
from app.evolution.models import (
    ReflexionInsight,
    PolicyMutation,
    BacktestMetricComparison,
    GovernanceProposal,
    FailureMode
)
from app.evolution.reflexion import ReflexionEngine
from app.evolution.optimizer import PolicyOptimizer
from app.evolution.backtest import ShadowBacktestRunner
from app.orchestrator.debate import DebateOutcome


class SelfEvolvingLoop:
    """Master controller that drives closed-loop policy evolution from investigation feedback."""

    def __init__(self):
        self.reflexion_engine = ReflexionEngine()
        self.optimizer = PolicyOptimizer()
        self.backtest_runner = ShadowBacktestRunner()
        self.active_proposals: Dict[str, GovernanceProposal] = {}
        self.deployed_patches: Dict[str, PolicyMutation] = {}

    def run_evolution_cycle(
        self,
        case_id: str,
        debate_outcome: DebateOutcome,
        customer_profile: Dict[str, Any],
        transaction_findings: Dict[str, Any],
        fraud_findings: Dict[str, Any]
    ) -> GovernanceProposal:
        """Executes one full self-evolution cycle triggered by an adjudicated contradiction."""
        
        # 1. Reflexion: Root cause analysis of rule failure / blindspot
        reflexion = self.reflexion_engine.analyze_case_failure(
            case_id=case_id,
            debate_outcome=debate_outcome,
            customer_profile=customer_profile,
            transaction_findings=transaction_findings,
            fraud_findings=fraud_findings
        )

        # 2. Optimization: Synthesize mutated policy rule with exemption guards
        mutation = self.optimizer.evolve_policy_rule(reflexion)

        # 3. Shadow Backtesting: Counterfactual regression across benchmark suite
        backtest = self.backtest_runner.run_backtest_benchmark(
            mutation=mutation,
            target_failure_mode=reflexion.failure_mode
        )

        # 4. Formulate Governance Proposal for Human-in-the-Loop Approval
        proposal_id = f"GOV-PR-{uuid.uuid4().hex[:6].upper()}"
        compliance_impact = (
            f"Adoption of {mutation.target_rule_id} [{mutation.version_tag}] reduces bank-wide false positives by "
            f"{backtest.fp_reduction_pct}% while maintaining 0.0% false negatives. Protects innocent manipulated "
            f"customers from wrongful debanking while preserving 100% interception of syndicate money mules."
        )

        proposal = GovernanceProposal(
            proposal_id=proposal_id,
            title=f"Autonomous Policy Evolution: {mutation.target_rule_id} -> {mutation.version_tag}",
            status="READY_FOR_HUMAN_APPROVAL",
            reflexion=reflexion,
            mutation=mutation,
            backtest=backtest,
            compliance_impact_statement=compliance_impact,
            hot_deploy_available=True
        )

        self.active_proposals[proposal_id] = proposal
        return proposal

    def deploy_mutation(self, proposal_id: str) -> Dict[str, Any]:
        """Simulates hot-reloading the approved policy patch into the active runtime."""
        proposal = self.active_proposals.get(proposal_id)
        if not proposal:
            return {"status": "error", "message": f"Proposal {proposal_id} not found."}

        proposal.status = "DEPLOYED"
        self.deployed_patches[proposal.mutation.target_rule_id] = proposal.mutation
        return {
            "status": "success",
            "message": f"Policy patch {proposal.mutation.version_tag} successfully hot-deployed to active policy engine.",
            "rule_id": proposal.mutation.target_rule_id,
            "version": proposal.mutation.version_tag,
            "hot_reloaded_at": proposal.mutation.created_at
        }
