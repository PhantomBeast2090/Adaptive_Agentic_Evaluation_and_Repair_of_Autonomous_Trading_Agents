"""Diagnostic state accumulator for adaptive diagnosis (E2-A).

``DiagnosticState`` is the minimal working memory of the future diagnostic
loop: baseline references, current competing hypotheses, committed
predictions, available and executed tests, results, hypothesis updates,
proposals, selection rationales, current uncertainty, budget usage, and
stopping reason.

Relationship to E0 (preserve, don't replace):

* The state constructs and owns a **fresh diagnostic-scope E0
  ``EvaluationState``** (its own ``diagnostic_id``; same agent, environment
  spec, config shape, and budget). Hypothesis registrations, test
  registrations, and test results are mirrored into it, so the standard
  E0 audit trail covers the diagnostic phase too.
* The E1 baseline artefact is never touched: the baseline enters only as
  ``(baseline_evaluation_id, baseline_fingerprint)`` references, and every
  ``DiagnosticTestResult`` re-states them. Counterfactual separation is
  structural — there is no code path from here back into baseline records.
* Updated hypothesis versions live **only** in ``DiagnosticState`` (the
  E0 mirror keeps the registration ledger; E0 has no update slot and must
  not change for E2-A). Full history is preserved in the update log.

Like E0's accumulator, this object is mutable only through explicit
append-only methods with tuple replacement. Ordering gates enforce the
diagnostic protocol: test → prediction → result → update, with proposals
grounded in registered rationales.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.evaluation_state import EvaluationState
from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw
from evaluation.contracts.hypotheses import Hypothesis
from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.contracts.hypothesis_updates import HypothesisUpdate
from evaluation.diagnostics.contracts.predictions import HypothesisPrediction
from evaluation.diagnostics.contracts.proposals import (
    DiagnosticProposal,
    SelectionRationale,
)
from evaluation.diagnostics.contracts.test_results import DiagnosticTestResult


@dataclass(frozen=True)
class UncertaintySnapshot:
    """Current diagnostic uncertainty, assessed by a named method.

    Minimal by design: which hypotheses remain open, under which method.
    History is not stored here — it is rebuildable from the update log.
    """

    assessment_id: str
    method: str
    version: str
    open_hypothesis_ids: Tuple[str, ...] = ()
    summary: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "assessment_id",
            "method",
            "version",
            "summary",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        ids = self.open_hypothesis_ids
        if isinstance(ids, str) or not isinstance(ids, (tuple, list)):
            raise TypeError(
                "open_hypothesis_ids must be a tuple/list of strings"
            )
        ids = tuple(ids)
        for item in ids:
            if not isinstance(item, str) or not item:
                raise ValueError(
                    "open_hypothesis_ids entries must be non-empty strings"
                )
        if len(set(ids)) != len(ids):
            raise ValueError("open_hypothesis_ids must not contain duplicates")
        object.__setattr__(self, "open_hypothesis_ids", ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "method": self.method,
            "version": self.version,
            "open_hypothesis_ids": list(self.open_hypothesis_ids),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintySnapshot":
        if not isinstance(payload, Mapping):
            raise TypeError("UncertaintySnapshot payload must be a mapping")
        known = {
            "assessment_id",
            "method",
            "version",
            "open_hypothesis_ids",
            "summary",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown UncertaintySnapshot fields: {sorted(extra)}"
            )
        try:
            return cls(
                assessment_id=payload["assessment_id"],
                method=payload["method"],
                version=payload["version"],
                open_hypothesis_ids=tuple(
                    payload.get("open_hypothesis_ids", ())
                ),
                summary=payload["summary"],
            )
        except KeyError as exc:
            raise ValueError(
                f"UncertaintySnapshot payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


class DiagnosticState:
    """Append-only working memory of one diagnostic episode."""

    def __init__(
        self,
        diagnostic_id: str,
        baseline_evaluation_id: str,
        baseline_fingerprint: str,
        agent_identity: AgentIdentity,
        environment_spec: Mapping[str, Any],
        config: Mapping[str, Any],
        budget: EvaluationBudget,
    ) -> None:
        if not isinstance(diagnostic_id, str) or not diagnostic_id.strip():
            raise ValueError("diagnostic_id must be a non-empty string")
        for field_name, value in (
            ("baseline_evaluation_id", baseline_evaluation_id),
            ("baseline_fingerprint", baseline_fingerprint),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(agent_identity, AgentIdentity):
            raise TypeError("agent_identity must be an AgentIdentity")
        if not isinstance(environment_spec, Mapping):
            raise TypeError("environment_spec must be a mapping")
        if not isinstance(config, Mapping):
            raise TypeError("config must be a mapping")
        if not isinstance(budget, EvaluationBudget):
            raise TypeError("budget must be an EvaluationBudget")
        self._diagnostic_id = diagnostic_id
        self._baseline_evaluation_id = baseline_evaluation_id
        self._baseline_fingerprint = baseline_fingerprint
        self._agent_identity = agent_identity
        self._environment_spec = freeze(dict(environment_spec))
        self._config = freeze(dict(config))
        self._budget = budget
        self._evaluation_state = EvaluationState(
            evaluation_id=diagnostic_id,
            agent_identity=agent_identity,
            environment_spec=dict(environment_spec),
            config=dict(config),
            budget=budget,
        )
        self._hypotheses: Dict[str, Hypothesis] = {}
        # Registration ledger: originals as registered, never replaced.
        # Current versions evolve via updates; the ledger mirrors the E0
        # state and enables exact replay in from_dict.
        self._registered: Dict[str, Hypothesis] = {}
        self._predictions: Dict[str, HypothesisPrediction] = {}
        self._tests: Dict[str, DiagnosticTest] = {}
        self._results: Dict[str, DiagnosticTestResult] = {}
        self._updates: Tuple[HypothesisUpdate, ...] = ()
        self._proposals: Dict[str, DiagnosticProposal] = {}
        self._rationales: Dict[str, SelectionRationale] = {}
        self._uncertainty: Optional[UncertaintySnapshot] = None
        self._stopping_reason: Optional[StoppingReason] = None

    # -- read access ---------------------------------------------------

    @property
    def diagnostic_id(self) -> str:
        return self._diagnostic_id

    @property
    def baseline_evaluation_id(self) -> str:
        return self._baseline_evaluation_id

    @property
    def baseline_fingerprint(self) -> str:
        return self._baseline_fingerprint

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
    def evaluation_state(self) -> EvaluationState:
        """The owned diagnostic-scope E0 accumulator (mirror ledger)."""
        return self._evaluation_state

    @property
    def hypotheses(self) -> Tuple[Hypothesis, ...]:
        return tuple(
            self._hypotheses[key] for key in sorted(self._hypotheses)
        )

    @property
    def predictions(self) -> Tuple[HypothesisPrediction, ...]:
        return tuple(
            self._predictions[key] for key in sorted(self._predictions)
        )

    @property
    def available_tests(self) -> Tuple[DiagnosticTest, ...]:
        return tuple(self._tests[key] for key in sorted(self._tests))

    @property
    def test_results(self) -> Tuple[DiagnosticTestResult, ...]:
        return tuple(self._results[key] for key in sorted(self._results))

    @property
    def hypothesis_updates(self) -> Tuple[HypothesisUpdate, ...]:
        return self._updates

    @property
    def proposals(self) -> Tuple[DiagnosticProposal, ...]:
        return tuple(
            self._proposals[key] for key in sorted(self._proposals)
        )

    @property
    def rationales(self) -> Tuple[SelectionRationale, ...]:
        return tuple(
            self._rationales[key] for key in sorted(self._rationales)
        )

    @property
    def uncertainty(self) -> Optional[UncertaintySnapshot]:
        return self._uncertainty

    @property
    def stopping_reason(self) -> Optional[StoppingReason]:
        return self._stopping_reason

    def hypothesis(self, hypothesis_id: str) -> Hypothesis:
        try:
            return self._hypotheses[hypothesis_id]
        except KeyError:
            raise KeyError(
                f"no registered hypothesis {hypothesis_id!r}"
            ) from None

    # -- budget ----------------------------------------------------------

    def tests_consumed(self) -> int:
        return len(self._results)

    def budget_usage(self) -> Dict[str, int]:
        return {"tests": len(self._results)}

    def budget_exhausted(self) -> bool:
        return self._budget.is_exhausted(self.budget_usage())

    # -- append-only accumulation ----------------------------------------

    def register_hypothesis(self, hypothesis: Hypothesis) -> None:
        if not isinstance(hypothesis, Hypothesis):
            raise TypeError("hypothesis must be a Hypothesis")
        if hypothesis.hypothesis_id in self._hypotheses:
            raise ValueError(
                f"duplicate hypothesis_id {hypothesis.hypothesis_id!r}"
            )
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        self._registered[hypothesis.hypothesis_id] = hypothesis
        self._evaluation_state.add_hypothesis(hypothesis)

    def register_test(self, test: DiagnosticTest) -> None:
        if not isinstance(test, DiagnosticTest):
            raise TypeError("test must be a DiagnosticTest")
        if test.test_id in self._tests:
            raise ValueError(f"duplicate test_id {test.test_id!r}")
        self._tests[test.test_id] = test
        self._evaluation_state.record_test(test)

    def record_prediction(self, prediction: HypothesisPrediction) -> None:
        if not isinstance(prediction, HypothesisPrediction):
            raise TypeError("prediction must be a HypothesisPrediction")
        if prediction.prediction_id in self._predictions:
            raise ValueError(
                f"duplicate prediction_id {prediction.prediction_id!r}"
            )
        if prediction.hypothesis_id not in self._hypotheses:
            raise ValueError(
                "prediction references unknown hypothesis "
                f"{prediction.hypothesis_id!r}: register the hypothesis first"
            )
        if prediction.test_id not in self._tests:
            raise ValueError(
                "prediction references unknown test "
                f"{prediction.test_id!r}: register the test first"
            )
        if prediction.pair() in {
            existing.pair() for existing in self._predictions.values()
        }:
            raise ValueError(
                "one prediction per (hypothesis, test) pair: "
                f"{prediction.pair()!r} is already committed"
            )
        self._predictions[prediction.prediction_id] = prediction

    def record_result(self, result: DiagnosticTestResult) -> None:
        if not isinstance(result, DiagnosticTestResult):
            raise TypeError("result must be a DiagnosticTestResult")
        if result.result_id in self._results:
            raise ValueError(f"duplicate result_id {result.result_id!r}")
        if result.test_id not in self._tests:
            raise ValueError(
                f"no registered test {result.test_id!r}: register the test "
                "before its result (no orphan results)"
            )
        if (
            result.baseline_evaluation_id != self._baseline_evaluation_id
            or result.baseline_fingerprint != self._baseline_fingerprint
        ):
            raise ValueError(
                "result baseline reference does not match this diagnostic "
                "episode's baseline"
            )
        if result.intervention_fingerprint != (
            self._tests[result.test_id].fingerprint()
        ):
            raise ValueError(
                "result intervention fingerprint does not match the "
                "registered test: results must run the specified intervention"
            )
        for prediction_id in result.prediction_ids:
            if prediction_id not in self._predictions:
                raise ValueError(
                    "result references uncommitted prediction "
                    f"{prediction_id!r}: predictions must exist before results"
                )
        self._results[result.result_id] = result
        self._evaluation_state.record_test_result(
            result.test_id,
            {
                "outcome": result.outcome,
                "result_id": result.result_id,
                "result_fingerprint": result.fingerprint(),
            },
        )

    def record_update(self, update: HypothesisUpdate) -> None:
        if not isinstance(update, HypothesisUpdate):
            raise TypeError("update must be a HypothesisUpdate")
        if update.update_id in {u.update_id for u in self._updates}:
            raise ValueError(f"duplicate update_id {update.update_id!r}")
        if update.hypothesis_id not in self._hypotheses:
            raise ValueError(
                f"update references unknown hypothesis "
                f"{update.hypothesis_id!r}"
            )
        if update.prediction_id not in self._predictions:
            raise ValueError(
                f"update references unknown prediction "
                f"{update.prediction_id!r}"
            )
        if update.result_id not in self._results:
            raise ValueError(
                f"update references unknown result {update.result_id!r}"
            )
        current = self._hypotheses[update.hypothesis_id]
        if update.prior_fingerprint != current.fingerprint():
            raise ValueError(
                "update prior does not match the current hypothesis "
                "version: updates apply to the version they assessed"
            )
        self._hypotheses[update.hypothesis_id] = update.updated
        self._updates = self._updates + (update,)

    def record_rationale(self, rationale: SelectionRationale) -> None:
        if not isinstance(rationale, SelectionRationale):
            raise TypeError("rationale must be a SelectionRationale")
        if rationale.rationale_id in self._rationales:
            raise ValueError(
                f"duplicate rationale_id {rationale.rationale_id!r}"
            )
        for candidate in rationale.candidates:
            if candidate.test_id not in self._tests:
                raise ValueError(
                    "rationale considers unregistered test "
                    f"{candidate.test_id!r}"
                )
        self._rationales[rationale.rationale_id] = rationale

    def record_proposal(self, proposal: DiagnosticProposal) -> None:
        if not isinstance(proposal, DiagnosticProposal):
            raise TypeError("proposal must be a DiagnosticProposal")
        if proposal.proposal_id in self._proposals:
            raise ValueError(
                f"duplicate proposal_id {proposal.proposal_id!r}"
            )
        for hypothesis_id in proposal.hypothesis_ids:
            if hypothesis_id not in self._hypotheses:
                raise ValueError(
                    f"proposal references unknown hypothesis {hypothesis_id!r}"
                )
        for prediction_id in proposal.prediction_ids:
            if prediction_id not in self._predictions:
                raise ValueError(
                    f"proposal references unknown prediction {prediction_id!r}"
                )
        if proposal.selected_test_id not in self._tests:
            raise ValueError(
                "proposal selects unregistered test "
                f"{proposal.selected_test_id!r}"
            )
        for test_id in proposal.alternative_test_ids:
            if test_id not in self._tests:
                raise ValueError(
                    f"proposal alternative references unregistered test "
                    f"{test_id!r}"
                )
        if proposal.rationale_id not in self._rationales:
            raise ValueError(
                "proposal references unrecorded rationale "
                f"{proposal.rationale_id!r}: record the rationale first"
            )
        self._proposals[proposal.proposal_id] = proposal

    def record_uncertainty(self, snapshot: UncertaintySnapshot) -> None:
        if not isinstance(snapshot, UncertaintySnapshot):
            raise TypeError("snapshot must be an UncertaintySnapshot")
        unknown = set(snapshot.open_hypothesis_ids) - set(self._hypotheses)
        if unknown:
            raise ValueError(
                "uncertainty references unregistered hypotheses: "
                f"{sorted(unknown)}"
            )
        self._uncertainty = snapshot

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
        self._evaluation_state.set_stopping_reason(reason)

    # -- serialization ---------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagnostic_id": self._diagnostic_id,
            "baseline_evaluation_id": self._baseline_evaluation_id,
            "baseline_fingerprint": self._baseline_fingerprint,
            "agent_identity": self._agent_identity.to_dict(),
            "environment_spec": copy.deepcopy(thaw(self._environment_spec)),
            "config": copy.deepcopy(thaw(self._config)),
            "budget": self._budget.to_dict(),
            "hypotheses": [
                self._hypotheses[key].to_dict()
                for key in sorted(self._hypotheses)
            ],
            "registered_hypotheses": [
                self._registered[key].to_dict()
                for key in sorted(self._registered)
            ],
            "predictions": [
                self._predictions[key].to_dict()
                for key in sorted(self._predictions)
            ],
            "available_tests": [
                self._tests[key].to_dict() for key in sorted(self._tests)
            ],
            "test_results": [
                self._results[key].to_dict() for key in sorted(self._results)
            ],
            "hypothesis_updates": [u.to_dict() for u in self._updates],
            "proposals": [
                self._proposals[key].to_dict()
                for key in sorted(self._proposals)
            ],
            "rationales": [
                self._rationales[key].to_dict()
                for key in sorted(self._rationales)
            ],
            "uncertainty": (
                self._uncertainty.to_dict()
                if self._uncertainty is not None
                else None
            ),
            "evaluation_state": self._evaluation_state.to_dict(),
            "stopping_reason": (
                self._stopping_reason.value
                if self._stopping_reason is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DiagnosticState":
        if not isinstance(payload, Mapping):
            raise TypeError("DiagnosticState payload must be a mapping")
        known = {
            "diagnostic_id", "baseline_evaluation_id",
            "baseline_fingerprint", "agent_identity", "environment_spec",
            "config", "budget", "hypotheses", "registered_hypotheses",
            "predictions",
            "available_tests", "test_results", "hypothesis_updates",
            "proposals", "rationales", "uncertainty", "evaluation_state",
            "stopping_reason",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown DiagnosticState fields: {sorted(extra)}"
            )
        try:
            state = cls(
                diagnostic_id=payload["diagnostic_id"],
                baseline_evaluation_id=payload["baseline_evaluation_id"],
                baseline_fingerprint=payload["baseline_fingerprint"],
                agent_identity=AgentIdentity.from_dict(
                    payload["agent_identity"]
                ),
                environment_spec=dict(payload.get("environment_spec", {})),
                config=dict(payload.get("config", {})),
                budget=EvaluationBudget.from_dict(payload["budget"]),
            )
        except KeyError as exc:
            raise ValueError(
                f"DiagnosticState payload missing {exc}"
            ) from exc
        registered = payload.get("registered_hypotheses")
        if registered is None:
            raise ValueError(
                "DiagnosticState payload missing 'registered_hypotheses': "
                "the registration ledger is required for exact replay"
            )
        for item in registered:
            state.register_hypothesis(Hypothesis.from_dict(item))
        for item in payload.get("available_tests", []):
            state.register_test(DiagnosticTest.from_dict(item))
        for item in payload.get("predictions", []):
            state.record_prediction(HypothesisPrediction.from_dict(item))
        for item in payload.get("test_results", []):
            state.record_result(DiagnosticTestResult.from_dict(item))
        for item in payload.get("hypothesis_updates", []):
            state.record_update(HypothesisUpdate.from_dict(item))
        replayed = sorted(
            h.fingerprint() for h in state.hypotheses
        )
        stored = sorted(
            Hypothesis.from_dict(item).fingerprint()
            for item in payload.get("hypotheses", [])
        )
        if replayed != stored:
            raise ValueError(
                "stored hypotheses do not match replayed update history: "
                "refusing to load an inconsistent diagnostic state"
            )
        for item in payload.get("rationales", []):
            state.record_rationale(SelectionRationale.from_dict(item))
        for item in payload.get("proposals", []):
            state.record_proposal(DiagnosticProposal.from_dict(item))
        if payload.get("uncertainty") is not None:
            state.record_uncertainty(
                UncertaintySnapshot.from_dict(payload["uncertainty"])
            )
        if payload.get("stopping_reason") is not None:
            state.set_stopping_reason(payload["stopping_reason"])
        rebuilt = state.to_dict()
        stored_state = dict(payload.get("evaluation_state", {}))
        if rebuilt["evaluation_state"] != stored_state:
            raise ValueError(
                "stored evaluation_state does not match replayed history: "
                "refusing to load an inconsistent diagnostic state"
            )
        return state

    def fingerprint(self) -> str:
        """Deterministic identity over the full diagnostic state.

        No exclusions: the state stores no wall-clock timestamps, process
        ids, or memory addresses.
        """
        return fingerprint_of_dict(self.to_dict())

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, DiagnosticState)
            and self.to_dict() == other.to_dict()
        )

    def __repr__(self) -> str:
        return (
            f"DiagnosticState(diagnostic_id={self._diagnostic_id!r}, "
            f"hypotheses={len(self._hypotheses)}, "
            f"predictions={len(self._predictions)}, "
            f"tests={len(self._tests)}, "
            f"results={len(self._results)}, "
            f"updates={len(self._updates)}, "
            f"stopping={self._stopping_reason})"
        )
