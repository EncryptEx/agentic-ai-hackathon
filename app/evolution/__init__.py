"""Self-Evolving Agent Loop Package.
Provides automated Reflexion, Policy Optimization, Shadow Backtesting, and Governance Proposals.
"""

from app.evolution.models import (
    FailureMode,
    ReflexionInsight,
    PolicyMutation,
    BacktestMetricComparison,
    GovernanceProposal,
)
from app.evolution.reflexion import ReflexionEngine
from app.evolution.optimizer import PolicyOptimizer
from app.evolution.backtest import ShadowBacktestRunner
from app.evolution.loop import SelfEvolvingLoop

__all__ = [
    "FailureMode",
    "ReflexionInsight",
    "PolicyMutation",
    "BacktestMetricComparison",
    "GovernanceProposal",
    "ReflexionEngine",
    "PolicyOptimizer",
    "ShadowBacktestRunner",
    "SelfEvolvingLoop",
]
