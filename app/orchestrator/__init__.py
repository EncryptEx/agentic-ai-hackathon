"""Dynamic Orchestrator & Multi-Agent Contradiction Debate Package for FRAML."""

from .triage import DynamicTriageRouter, CaseTopology
from .debate import ContradictionDetector, DialecticDebateEngine, DebateOutcome, ConflictType

__all__ = [
    "DynamicTriageRouter",
    "CaseTopology",
    "ContradictionDetector",
    "DialecticDebateEngine",
    "DebateOutcome",
    "ConflictType",
]
