"""E0 evaluator contracts: stable interfaces for adaptive evaluation.

This package establishes the deterministic contracts on which the later
evaluator architecture (E1 baseline, E2 adaptive diagnosis, E3 repair,
E4 validation + learning) will be built. It contains representations
only: no LLM, no adaptive selector, no repair behavior, no learning.

Contracts:

* ``agent`` — target-agent structural contract (``TargetAgent``,
  ``AgentIdentity``, ``invoke_act``).
* ``decision_record`` — raw observable decision events (``DecisionRecord``).
* ``evidence`` — derived behavioral claims (``BehavioralEvidence``).
* ``hypotheses`` — competing failure-mechanism claims (``Hypothesis``).
* ``diagnostic_tests`` — first-class test descriptors (``DiagnosticTest``).
* ``evaluation_state`` — central accumulative record (``EvaluationState``).
* ``budget`` — explicit limits (``EvaluationBudget``).
* ``stopping`` — termination vocabulary (``StoppingReason``).
* ``fingerprints`` — canonicalization + SHA-256 mechanism.
* ``oracle`` — leakage boundary (``TargetObservation``/``OraclePacket``).
"""

from evaluation.contracts.agent import (
    AgentIdentity,
    TargetAgent,
    invoke_act,
    is_valid_target_agent,
    validate_target_agent,
)
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.evaluation_state import EvaluationState
from evaluation.contracts.evidence import BehavioralEvidence, EvidenceCategory
from evaluation.contracts.fingerprints import (
    canonicalize,
    fingerprint,
    fingerprint_of_dict,
)
from evaluation.contracts.hypotheses import Hypothesis, HypothesisStatus
from evaluation.contracts.oracle import OraclePacket, TargetObservation
from evaluation.contracts.stopping import StoppingReason

__all__ = [
    "AgentIdentity",
    "TargetAgent",
    "invoke_act",
    "is_valid_target_agent",
    "validate_target_agent",
    "EvaluationBudget",
    "DecisionRecord",
    "DiagnosticTest",
    "EvaluationState",
    "BehavioralEvidence",
    "EvidenceCategory",
    "canonicalize",
    "fingerprint",
    "fingerprint_of_dict",
    "Hypothesis",
    "HypothesisStatus",
    "OraclePacket",
    "TargetObservation",
    "StoppingReason",
]
