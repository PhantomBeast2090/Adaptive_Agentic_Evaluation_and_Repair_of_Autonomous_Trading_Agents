"""Candidate eligibility and per-candidate statistics (E2-D).

:func:`eligible_candidates` filters registered tests against the frozen
state without mutating anything; :func:`candidate_statistics` computes
the (D, C, cost) triple each eligible candidate contributes to the
lexicographic key. Both are pure functions of the diagnostic state —
deterministic, versioned via ``methodology.py``, free of environment,
market, Bayesian, and ranking concepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Tuple

from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.predictions import HypothesisPrediction
from evaluation.diagnostics.interpretation.methodology import OPEN_STATUSES


@dataclass(frozen=True)
class EligibilityVerdict:
    """Eligibility verdict for one registered test (internal planning)."""

    test_id: str
    eligible: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.test_id, str) or not self.test_id.strip():
            raise ValueError("test_id must be a non-empty string")
        if not isinstance(self.eligible, bool):
            raise TypeError("eligible must be a bool")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")


@dataclass(frozen=True)
class CandidateStatistics:
    """Structured facts behind one eligible candidate's selection key."""

    test_id: str
    discrimination_pairs: int
    open_coverage: int
    estimated_cost: float
    open_predictions: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.test_id, str) or not self.test_id.strip():
            raise ValueError("test_id must be a non-empty string")
        for field_name in ("discrimination_pairs", "open_coverage"):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative int")
        cost = self.estimated_cost
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or cost != cost
            or cost in (float("inf"), float("-inf"))
            or float(cost) < 0
        ):
            raise ValueError("estimated_cost must be a finite non-negative number")
        object.__setattr__(self, "estimated_cost", float(cost))

    def selection_key(self) -> Tuple[int, int, float, str]:
        """Lexicographic key: (-D, -C, cost, test_id)."""
        return (
            -self.discrimination_pairs,
            -self.open_coverage,
            self.estimated_cost,
            self.test_id,
        )


def _open_hypothesis_ids(state: DiagnosticState) -> Tuple[str, ...]:
    return tuple(
        sorted(
            h.hypothesis_id
            for h in state.hypotheses
            if h.status.value in OPEN_STATUSES
        )
    )


def eligible_candidates(
    state: DiagnosticState,
) -> Tuple[Tuple[DiagnosticTest, ...], Tuple[EligibilityVerdict, ...]]:
    """Split registered tests into eligible candidates and verdicts.

    A test is eligible only if it is registered, has no recorded result,
    and carries at least one committed prediction for a currently OPEN
    hypothesis. Every exclusion states its reason; nothing is silent.
    """
    if not isinstance(state, DiagnosticState):
        raise TypeError(
            "state must be a DiagnosticState, "
            f"got {type(state).__name__}"
        )
    open_ids = set(_open_hypothesis_ids(state))
    executed = {
        result.test_id for result in state.test_results
    }
    predictions_by_test: Dict[str, List[HypothesisPrediction]] = {}
    for prediction in state.predictions:
        predictions_by_test.setdefault(prediction.test_id, []).append(
            prediction
        )
    eligible: List[DiagnosticTest] = []
    verdicts: List[EligibilityVerdict] = []
    for test in sorted(state.available_tests, key=lambda t: t.test_id):
        if test.test_id in executed:
            verdicts.append(
                EligibilityVerdict(
                    test_id=test.test_id,
                    eligible=False,
                    reason="already executed with a recorded result",
                )
            )
            continue
        open_predictions = [
            p
            for p in predictions_by_test.get(test.test_id, [])
            if p.hypothesis_id in open_ids
        ]
        if not open_predictions:
            verdicts.append(
                EligibilityVerdict(
                    test_id=test.test_id,
                    eligible=False,
                    reason=(
                        "no committed prediction for a currently open "
                        "hypothesis"
                    ),
                )
            )
            continue
        eligible.append(test)
        verdicts.append(
            EligibilityVerdict(
                test_id=test.test_id,
                eligible=True,
                reason=(
                    f"{len(open_predictions)} committed open-hypothesis "
                    "prediction(s)"
                ),
            )
        )
    return tuple(eligible), tuple(verdicts)


def candidate_statistics(
    state: DiagnosticState, test: DiagnosticTest
) -> CandidateStatistics:
    """Compute (D, C, cost) for one eligible candidate test."""
    if not isinstance(state, DiagnosticState):
        raise TypeError(
            "state must be a DiagnosticState, "
            f"got {type(state).__name__}"
        )
    if not isinstance(test, DiagnosticTest):
        raise TypeError(
            f"test must be a DiagnosticTest, got {type(test).__name__}"
        )
    open_ids = set(_open_hypothesis_ids(state))
    by_hypothesis: Dict[str, str] = {}
    for prediction in state.predictions:
        if (
            prediction.test_id == test.test_id
            and prediction.hypothesis_id in open_ids
        ):
            by_hypothesis.setdefault(
                prediction.hypothesis_id,
                prediction.expected_direction.value,
            )
    pairs = sum(
        1
        for first, second in combinations(sorted(by_hypothesis), 2)
        if by_hypothesis[first] != by_hypothesis[second]
    )
    return CandidateStatistics(
        test_id=test.test_id,
        discrimination_pairs=pairs,
        open_coverage=len(by_hypothesis),
        estimated_cost=test.estimated_cost,
        open_predictions=tuple(
            sorted(
                (hypothesis_id, test.test_id)
                for hypothesis_id in by_hypothesis
            )
        ),
    )


def open_hypothesis_ids(state: DiagnosticState) -> Tuple[str, ...]:
    """Sorted ids of currently open hypotheses (public helper)."""
    if not isinstance(state, DiagnosticState):
        raise TypeError(
            "state must be a DiagnosticState, "
            f"got {type(state).__name__}"
        )
    return _open_hypothesis_ids(state)
