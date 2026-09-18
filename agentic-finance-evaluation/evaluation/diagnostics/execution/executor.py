"""Deterministic diagnostic test executor (E2-B).

:func:`execute` runs one already-registered ``DiagnosticTest`` with
already-committed predictions against an isolated diagnostic episode of
the target agent::

    DiagnosticTest (registered)
          |
          v
    E2-B Executor
          |
       +--+----------------+
       |                   |
       v                   v
    Intervention       Fresh Episode
    (materialised      (fresh env +
     into env            agent reset)
     config)               |
       |                   |
       +---------+---------+
                 |
                 v
          TargetObservation (E1 trusted path)
                 |
                 v
             Agent.act() via invoke_act
                 |
                 v
          Environment.step() (sole authority)
                 |
                 v
          DecisionRecords (episode-owned)
                 |
                 v
          Diagnostic Metrics (named measures)
                 |
                 v
       DiagnosticTestResult -> DiagnosticState

The executor decides nothing adaptive: no hypothesis judgement, no test
choice, no scoring, no inference, no repair. It executes the test it is
given and reports observations; interpretation belongs to later
milestones (``HypothesisUpdate``).

Failure contract: caller errors (unregistered test, uncommitted or
mismatched predictions, exhausted budget, duplicate execution identity)
raise before execution. Unmaterialisable interventions and bad episode
scope produce recorded ``INVALID`` results. Mid-run failures produce
recorded ``FAILED`` results preserving whatever evidence is legitimate.
The E1 baseline is never touched — it enters only as reference identity.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from environment.indian.environment import IndianMultiAssetEnvironment
from evaluation.baseline.metrics import METRIC_FUNCTIONS, MetricResult, compute_all
from evaluation.baseline.runner import _build_record, _validation_entries
from evaluation.baseline.trusted import observe_current
from evaluation.contracts.agent import invoke_act, validate_target_agent
from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.test_results import (
    DiagnosticExecutionStatus,
    DiagnosticTestResult,
)
from evaluation.diagnostics.execution.episode import (
    DiagnosticEpisode,
    DiagnosticEpisodeConfig,
)
from evaluation.diagnostics.execution.identity import (
    episode_id,
    execution_fingerprint,
    result_id_for,
)
from evaluation.diagnostics.execution.interventions import (
    InvalidIntervention,
    resolve_env_config,
)

EXECUTOR_METHOD = "e2b-deterministic-executor"
EXECUTOR_VERSION = "v1"

KNOWN_MEASURES = frozenset(function.__name__ for function in METRIC_FUNCTIONS)


def _resolve_predictions(
    state: DiagnosticState, test_id: str, prediction_ids: Sequence[str]
) -> List[str]:
    if isinstance(prediction_ids, str) or not isinstance(
        prediction_ids, (tuple, list)
    ):
        raise TypeError("prediction_ids must be a non-empty tuple/list")
    ids = list(prediction_ids)
    if not ids:
        raise ValueError(
            "at least one committed prediction is required to execute a test"
        )
    committed = {p.prediction_id: p for p in state.predictions}
    for prediction_id in ids:
        if not isinstance(prediction_id, str) or not prediction_id:
            raise TypeError("prediction ids must be non-empty strings")
        prediction = committed.get(prediction_id)
        if prediction is None:
            raise ValueError(
                f"prediction {prediction_id!r} is not committed: "
                "predictions must exist before execution"
            )
        if prediction.test_id != test_id:
            raise ValueError(
                f"prediction {prediction_id!r} belongs to test "
                f"{prediction.test_id!r}, not selected test {test_id!r}"
            )
    if len(set(ids)) != len(ids):
        raise ValueError("prediction_ids must not contain duplicates")
    return ids


def _invalid_result(
    *,
    test: DiagnosticTest,
    prediction_ids: Sequence[str],
    execution_fp: str,
    baseline_evaluation_id: str,
    baseline_fingerprint: str,
    reason: str,
) -> DiagnosticTestResult:
    return DiagnosticTestResult(
        result_id=result_id_for(execution_fp),
        test_id=test.test_id,
        execution_fingerprint=execution_fp,
        baseline_evaluation_id=baseline_evaluation_id,
        baseline_fingerprint=baseline_fingerprint,
        intervention_fingerprint=test.fingerprint(),
        record_fps=(),
        evidence_refs=(),
        measured=(),
        prediction_ids=tuple(prediction_ids),
        status=DiagnosticExecutionStatus.INVALID,
        error=reason,
        provenance_method=EXECUTOR_METHOD,
        provenance_version=EXECUTOR_VERSION,
    )


def execute(
    *,
    diagnostic_state: DiagnosticState,
    test_id: str,
    prediction_ids: Sequence[str],
    target_agent: Any,
    episode_config: DiagnosticEpisodeConfig,
) -> DiagnosticEpisode:
    """Execute one registered diagnostic test in an isolated episode.

    Args:
        diagnostic_state: working memory holding the registered test,
            committed predictions, budget, and baseline references. The
            result is registered here; nothing else is mutated.
        test_id: id of the registered ``DiagnosticTest`` to run.
        prediction_ids: committed predictions this execution adjudicates;
            every id must be registered and belong to ``test_id``.
        target_agent: structurally valid target agent. Receives only
            ``TargetObservation`` through ``invoke_act``.
        episode_config: window, universe, seed, and data root for the
            diagnostic episode.

    Returns:
        The ``DiagnosticEpisode`` (result plus its own trajectory).

    Raises:
        TypeError: wrong argument types, invalid agent, malformed agent
            output shape at the boundary (converted to FAILED, see below).
        ValueError: unregistered test, uncommitted/mismatched predictions,
            exhausted test budget, or duplicate execution identity.
    """
    if not isinstance(diagnostic_state, DiagnosticState):
        raise TypeError(
            "diagnostic_state must be a DiagnosticState, "
            f"got {type(diagnostic_state).__name__}"
        )
    if not isinstance(test_id, str) or not test_id:
        raise TypeError("test_id must be a non-empty string")
    if not isinstance(episode_config, DiagnosticEpisodeConfig):
        raise TypeError(
            "episode_config must be a DiagnosticEpisodeConfig, "
            f"got {type(episode_config).__name__}"
        )
    agent_errors = validate_target_agent(target_agent)
    if agent_errors:
        raise TypeError(f"invalid target agent: {agent_errors}")

    known_tests = {t.test_id: t for t in diagnostic_state.available_tests}
    test = known_tests.get(test_id)
    if test is None:
        raise ValueError(
            f"test {test_id!r} is not registered: "
            "register the test before execution"
        )
    resolved_predictions = _resolve_predictions(
        diagnostic_state, test_id, prediction_ids
    )
    if diagnostic_state.budget.is_exhausted(
        {"tests": diagnostic_state.tests_consumed()}
    ):
        raise ValueError(
            "diagnostic test budget exhausted: execution refused"
        )

    agent = target_agent
    agent_id = agent.identity.agent_id
    agent_version = agent.identity.version
    ep_id = episode_id(
        diagnostic_state.diagnostic_id, test_id, episode_config.seed
    )
    exec_fp = execution_fingerprint(
        diagnostic_id=diagnostic_state.diagnostic_id,
        test_id=test_id,
        test_fingerprint=test.fingerprint(),
        intervention_fingerprint=test.fingerprint(),
        episode_config_identity=episode_config.identity_dict(),
        agent_id=agent_id,
        agent_version=agent_version,
        baseline_evaluation_id=diagnostic_state.baseline_evaluation_id,
        baseline_fingerprint=diagnostic_state.baseline_fingerprint,
        episode_id_value=ep_id,
    )
    for existing in diagnostic_state.test_results:
        if existing.execution_fingerprint == exec_fp:
            raise ValueError(
                "duplicate execution identity: this semantic execution "
                f"is already recorded as {existing.result_id!r}; "
                "repeat executions must differ in seed, agent, "
                "configuration, or intervention"
            )

    def invalid(reason: str) -> DiagnosticEpisode:
        result = _invalid_result(
            test=test,
            prediction_ids=resolved_predictions,
            execution_fp=exec_fp,
            baseline_evaluation_id=diagnostic_state.baseline_evaluation_id,
            baseline_fingerprint=diagnostic_state.baseline_fingerprint,
            reason=reason,
        )
        diagnostic_state.record_result(result)
        return DiagnosticEpisode(
            episode_id=ep_id,
            diagnostic_id=diagnostic_state.diagnostic_id,
            test_id=test_id,
            execution_fingerprint=exec_fp,
            result=result,
            decision_records=(),
        )

    try:
        env_config = resolve_env_config(
            intervention=dict(test.intervention),
            baseline_spec=diagnostic_state.environment_spec,
            window=(episode_config.start_date, episode_config.end_date),
            episode_universe=dict(episode_config.universe),
        )
    except InvalidIntervention as exc:
        return invalid(f"invalid intervention: {exc.reason}")

    unknown_measures = [
        name for name in test.measures if name not in KNOWN_MEASURES
    ]
    if unknown_measures:
        return invalid(
            "unknown measures requested by test: "
            f"{sorted(unknown_measures)}"
        )

    try:
        env = IndianMultiAssetEnvironment(
            env_config, base_dir=episode_config.base_dir
        )
        spec = env.spec()
    except ValueError as exc:
        return invalid(f"invalid episode environment: {exc}")

    records: List[DecisionRecord] = []
    agent.reset()
    env.reset()  # lifecycle effect only; observations via trusted path
    try:
        while not env.done:
            if len(records) >= len(env.grid):
                raise RuntimeError(
                    "environment did not terminate within its decision grid"
                )
            session_index = env.index
            observation = observe_current(env)
            orders = [dict(order) for order in invoke_act(agent, observation)]
            validation = _validation_entries(orders, env)
            _, info, finished, meta = env.step(orders)
            records.append(
                _build_record(
                    observation,
                    orders,
                    validation,
                    dict(info),
                    session_index,
                    spec["market_fingerprint"],
                    str(meta.get("reason", "")) if finished else "",
                    finished,
                )
            )
    except Exception as exc:  # noqa: BLE001 - converted to FAILED result
        failed = DiagnosticTestResult(
            result_id=result_id_for(exec_fp),
            test_id=test_id,
            execution_fingerprint=exec_fp,
            baseline_evaluation_id=diagnostic_state.baseline_evaluation_id,
            baseline_fingerprint=diagnostic_state.baseline_fingerprint,
            intervention_fingerprint=test.fingerprint(),
            record_fps=tuple(r.fingerprint() for r in records),
            evidence_refs=(),
            measured=(),
            prediction_ids=tuple(resolved_predictions),
            status=DiagnosticExecutionStatus.FAILED,
            error=f"{type(exc).__name__}: {exc}",
            provenance_method=EXECUTOR_METHOD,
            provenance_version=EXECUTOR_VERSION,
        )
        diagnostic_state.record_result(failed)
        return DiagnosticEpisode(
            episode_id=ep_id,
            diagnostic_id=diagnostic_state.diagnostic_id,
            test_id=test_id,
            execution_fingerprint=exec_fp,
            result=failed,
            decision_records=tuple(records),
        )

    measured = compute_all(records, float(env_config["initial_cash"]))
    by_name = {metric.name: metric for metric in measured}
    result = DiagnosticTestResult(
        result_id=result_id_for(exec_fp),
        test_id=test_id,
        execution_fingerprint=exec_fp,
        baseline_evaluation_id=diagnostic_state.baseline_evaluation_id,
        baseline_fingerprint=diagnostic_state.baseline_fingerprint,
        intervention_fingerprint=test.fingerprint(),
        record_fps=tuple(r.fingerprint() for r in records),
        evidence_refs=(),
        measured=tuple(by_name[name] for name in test.measures),
        prediction_ids=tuple(resolved_predictions),
        status=DiagnosticExecutionStatus.COMPLETED,
        error=None,
        provenance_method=EXECUTOR_METHOD,
        provenance_version=EXECUTOR_VERSION,
    )
    diagnostic_state.record_result(result)
    return DiagnosticEpisode(
        episode_id=ep_id,
        diagnostic_id=diagnostic_state.diagnostic_id,
        test_id=test_id,
        execution_fingerprint=exec_fp,
        result=result,
        decision_records=tuple(records),
    )
