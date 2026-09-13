"""EvaluationState: the central accumulative evaluation record (E0).

An ``EvaluationState`` reconstructs one evaluation: who was evaluated
(:class:`AgentIdentity`), in which environment (frozen ``environment_spec``
carrying the environment's ``market_fingerprint``), under which config and
budget, and what has accumulated so far — baseline evidence, behavioral
evidence, hypotheses, executed tests and their results, budget, and the
terminal stopping reason.

Unlike the event/claim contracts (frozen dataclasses), the state is an
**accumulator** and therefore mutable. Mutation is disciplined:

* internal collections are tuples, replaced (``self._x = self._x + (i,)``)
  rather than mutated in place;
* every addition goes through an explicit append-only validator method;
* test results reference previously recorded tests (no orphan results);
* duplicate test/evidence/hypothesis ids are rejected (stable identity);
* the stopping reason is set once (re-setting to a different reason
  raises);
* repair/validation/regression slots exist as explicitly-typed opaque
  placeholders so E1/E2 serialization shapes stay stable, but no repair
  behavior lives here (E3).

The state is serializable (``to_dict``/``from_dict`` round-trip equality),
deterministic, and fingerprinted. No wall-clock timestamp is stored, so
the fingerprint needs no exclusions. No database, no network.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Tuple

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.evidence import BehavioralEvidence
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw
from evaluation.contracts.hypotheses import Hypothesis
from evaluation.contracts.stopping import StoppingReason


class EvaluationState:
    """Append-only accumulative record of one evaluation."""

    def __init__(
        self,
        evaluation_id: str,
        agent_identity: AgentIdentity,
        environment_spec: Mapping[str, Any],
        config: Mapping[str, Any],
        budget: EvaluationBudget,
    ) -> None:
        if not isinstance(evaluation_id, str) or not evaluation_id.strip():
            raise ValueError("evaluation_id must be a non-empty string")
        if not isinstance(agent_identity, AgentIdentity):
            raise TypeError("agent_identity must be an AgentIdentity")
        if not isinstance(environment_spec, Mapping):
            raise TypeError("environment_spec must be a mapping")
        environment_spec = dict(environment_spec)
        marker = environment_spec.get("market_fingerprint")
        if not isinstance(marker, str) or not marker:
            raise ValueError(
                "environment_spec must carry a non-empty "
                "'market_fingerprint' tying the evaluation to its environment"
            )
        if not isinstance(config, Mapping):
            raise TypeError("config must be a mapping")
        if not isinstance(budget, EvaluationBudget):
            raise TypeError("budget must be an EvaluationBudget")
        self._evaluation_id = evaluation_id
        self._agent_identity = agent_identity
        self._environment_spec = freeze(environment_spec)
        self._config = freeze(config)
        self._budget = budget
        self._baseline_evidence: Tuple[BehavioralEvidence, ...] = ()
        self._evidence: Tuple[BehavioralEvidence, ...] = ()
        self._hypotheses: Tuple[Hypothesis, ...] = ()
        self._executed_tests: Tuple[DiagnosticTest, ...] = ()
        self._test_results: Tuple[Mapping[str, Any], ...] = ()
        self._repair_candidates: Tuple[Mapping[str, Any], ...] = ()
        self._validation_results: Tuple[Mapping[str, Any], ...] = ()
        self._regressions: Tuple[Mapping[str, Any], ...] = ()
        self._stopping_reason: Optional[StoppingReason] = None

    # -- read access ---------------------------------------------------

    @property
    def evaluation_id(self) -> str:
        return self._evaluation_id

    @property
    def agent_identity(self) -> AgentIdentity:
        return self._agent_identity

    @property
    def environment_spec(self) -> Dict[str, Any]:
        return thaw(self._environment_spec)

    @property
    def config(self) -> Dict[str, Any]:
        return thaw(self._config)

    @property
    def budget(self) -> EvaluationBudget:
        return self._budget

    @property
    def baseline_evidence(self) -> Tuple[BehavioralEvidence, ...]:
        return self._baseline_evidence

    @property
    def evidence(self) -> Tuple[BehavioralEvidence, ...]:
        return self._evidence

    @property
    def hypotheses(self) -> Tuple[Hypothesis, ...]:
        return self._hypotheses

    @property
    def executed_tests(self) -> Tuple[DiagnosticTest, ...]:
        return self._executed_tests

    @property
    def test_results(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(thaw(result) for result in self._test_results)

    @property
    def repair_candidates(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(thaw(item) for item in self._repair_candidates)

    @property
    def validation_results(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(thaw(item) for item in self._validation_results)

    @property
    def regressions(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(thaw(item) for item in self._regressions)

    @property
    def stopping_reason(self) -> Optional[StoppingReason]:
        return self._stopping_reason

    # -- append-only accumulation --------------------------------------

    def _known_evidence_ids(self) -> set:
        return {e.evidence_id for e in self._baseline_evidence} | {
            e.evidence_id for e in self._evidence
        }

    def add_baseline_evidence(self, evidence: BehavioralEvidence) -> None:
        if not isinstance(evidence, BehavioralEvidence):
            raise TypeError("baseline evidence must be BehavioralEvidence")
        if evidence.evidence_id in self._known_evidence_ids():
            raise ValueError(
                f"duplicate evidence_id {evidence.evidence_id!r}"
            )
        self._baseline_evidence = self._baseline_evidence + (evidence,)

    def add_evidence(self, evidence: BehavioralEvidence) -> None:
        if not isinstance(evidence, BehavioralEvidence):
            raise TypeError("evidence must be BehavioralEvidence")
        if evidence.evidence_id in self._known_evidence_ids():
            raise ValueError(
                f"duplicate evidence_id {evidence.evidence_id!r}"
            )
        self._evidence = self._evidence + (evidence,)

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        if not isinstance(hypothesis, Hypothesis):
            raise TypeError("hypothesis must be a Hypothesis")
        known = {h.hypothesis_id for h in self._hypotheses}
        if hypothesis.hypothesis_id in known:
            raise ValueError(
                f"duplicate hypothesis_id {hypothesis.hypothesis_id!r}"
            )
        self._hypotheses = self._hypotheses + (hypothesis,)

    def record_test(self, test: DiagnosticTest) -> None:
        if not isinstance(test, DiagnosticTest):
            raise TypeError("test must be a DiagnosticTest")
        known = {t.test_id for t in self._executed_tests}
        if test.test_id in known:
            raise ValueError(f"duplicate test_id {test.test_id!r}")
        self._executed_tests = self._executed_tests + (test,)

    def record_test_result(
        self, test_id: str, result: Mapping[str, Any]
    ) -> None:
        if not isinstance(test_id, str) or not test_id:
            raise ValueError("test_id must be a non-empty string")
        if test_id not in {t.test_id for t in self._executed_tests}:
            raise ValueError(
                f"no executed test {test_id!r}: record the test before "
                "its result (no orphan results)"
            )
        if not isinstance(result, Mapping):
            raise TypeError("result must be a mapping")
        outcome = result.get("outcome")
        if not isinstance(outcome, str) or not outcome:
            raise ValueError("result must carry a non-empty 'outcome' string")
        stored = dict(result)
        stored["test_id"] = test_id
        self._test_results = self._test_results + (freeze(stored),)

    def note_repair_candidate(self, candidate: Mapping[str, Any]) -> None:
        """Record an opaque repair-candidate placeholder (E3 will type it)."""
        if not isinstance(candidate, Mapping):
            raise TypeError("repair candidate must be a mapping")
        if (
            not isinstance(candidate.get("candidate_id"), str)
            or not candidate["candidate_id"]
        ):
            raise ValueError(
                "repair candidate must carry a non-empty 'candidate_id'"
            )
        self._repair_candidates = self._repair_candidates + (freeze(candidate),)

    def note_validation_result(self, result: Mapping[str, Any]) -> None:
        """Record an opaque validation-result placeholder (E4 will type it)."""
        if not isinstance(result, Mapping):
            raise TypeError("validation result must be a mapping")
        if (
            not isinstance(result.get("candidate_id"), str)
            or not result["candidate_id"]
        ):
            raise ValueError(
                "validation result must carry a non-empty 'candidate_id'"
            )
        self._validation_results = self._validation_results + (freeze(result),)

    def note_regression(self, regression: Mapping[str, Any]) -> None:
        """Record an opaque regression placeholder (E4 will type it)."""
        if not isinstance(regression, Mapping):
            raise TypeError("regression must be a mapping")
        if (
            not isinstance(regression.get("description"), str)
            or not regression["description"]
        ):
            raise ValueError(
                "regression must carry a non-empty 'description'"
            )
        self._regressions = self._regressions + (freeze(regression),)

    def set_stopping_reason(
        self, reason: StoppingReason | str
    ) -> None:
        if isinstance(reason, str) and not isinstance(reason, StoppingReason):
            reason = StoppingReason.from_str(reason)
        if not isinstance(reason, StoppingReason):
            raise TypeError(
                f"reason must be a StoppingReason, got {reason!r}"
            )
        if (
            self._stopping_reason is not None
            and self._stopping_reason is not reason
        ):
            raise ValueError(
                "stopping reason is already set to "
                f"{self._stopping_reason.value}; refusing to overwrite with "
                f"{reason.value}"
            )
        self._stopping_reason = reason

    # -- serialization ---------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self._evaluation_id,
            "agent_identity": self._agent_identity.to_dict(),
            "environment_spec": thaw(self._environment_spec),
            "config": thaw(self._config),
            "baseline_evidence": [e.to_dict() for e in self._baseline_evidence],
            "evidence": [e.to_dict() for e in self._evidence],
            "hypotheses": [h.to_dict() for h in self._hypotheses],
            "executed_tests": [t.to_dict() for t in self._executed_tests],
            "test_results": [thaw(r) for r in self._test_results],
            "repair_candidates": [thaw(r) for r in self._repair_candidates],
            "validation_results": [thaw(r) for r in self._validation_results],
            "regressions": [thaw(r) for r in self._regressions],
            "budget": self._budget.to_dict(),
            "stopping_reason": (
                self._stopping_reason.value
                if self._stopping_reason is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvaluationState":
        if not isinstance(payload, Mapping):
            raise TypeError("EvaluationState payload must be a mapping")
        known = {
            "evaluation_id", "agent_identity", "environment_spec",
            "config", "baseline_evidence", "evidence", "hypotheses",
            "executed_tests", "test_results", "repair_candidates",
            "validation_results", "regressions", "budget",
            "stopping_reason",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown EvaluationState fields: {sorted(extra)}"
            )
        try:
            state = cls(
                evaluation_id=payload["evaluation_id"],
                agent_identity=AgentIdentity.from_dict(
                    payload["agent_identity"]
                ),
                environment_spec=dict(payload["environment_spec"]),
                config=dict(payload.get("config", {})),
                budget=EvaluationBudget.from_dict(payload["budget"]),
            )
        except KeyError as exc:
            raise ValueError(
                f"EvaluationState payload missing {exc}"
            ) from exc
        for item in payload.get("baseline_evidence", []):
            state.add_baseline_evidence(BehavioralEvidence.from_dict(item))
        for item in payload.get("evidence", []):
            state.add_evidence(BehavioralEvidence.from_dict(item))
        for item in payload.get("hypotheses", []):
            state.add_hypothesis(Hypothesis.from_dict(item))
        tests_by_id = {}
        for item in payload.get("executed_tests", []):
            test = DiagnosticTest.from_dict(item)
            state.record_test(test)
            tests_by_id[test.test_id] = test
        for item in payload.get("test_results", []):
            if not isinstance(item, Mapping) or "test_id" not in item:
                raise ValueError(
                    "test_results entries must carry 'test_id'"
                )
            stored = dict(item)
            test_id = stored.pop("test_id")
            state.record_test_result(test_id, stored)
        for item in payload.get("repair_candidates", []):
            state.note_repair_candidate(item)
        for item in payload.get("validation_results", []):
            state.note_validation_result(item)
        for item in payload.get("regressions", []):
            state.note_regression(item)
        if payload.get("stopping_reason") is not None:
            state.set_stopping_reason(payload["stopping_reason"])
        return state

    def fingerprint(self) -> str:
        """Deterministic identity over the full serialized state.

        No exclusions: the state stores no wall-clock timestamps,
        process ids, or memory addresses.
        """
        return fingerprint_of_dict(self.to_dict())

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, EvaluationState)
            and self.to_dict() == other.to_dict()
        )

    def __repr__(self) -> str:
        return (
            f"EvaluationState(evaluation_id={self._evaluation_id!r}, "
            f"agent={self._agent_identity}, "
            f"evidence={len(self._evidence)}, "
            f"hypotheses={len(self._hypotheses)}, "
            f"tests={len(self._executed_tests)}, "
            f"stopping={self._stopping_reason})"
        )
