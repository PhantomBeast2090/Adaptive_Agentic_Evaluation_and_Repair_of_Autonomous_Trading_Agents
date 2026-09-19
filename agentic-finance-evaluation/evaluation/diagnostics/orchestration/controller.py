"""Closed-loop diagnostic orchestration controller (E2-E).

:func:`run` drives one deterministic adaptive diagnostic loop over a
supplied ``DiagnosticState``:

1. ask E2-D for the next proposal from current state;
2. on ``NoCandidateResult``, terminate without executing;
3. otherwise execute the preferred test through E2-B;
4. on a non-COMPLETED result, record the failure explicitly in the
   trace and continue selecting (the failed test is consumed by
   registration, so it can never be re-proposed);
5. on a COMPLETED result, interpret through E2-C against the frozen
   baseline artefact;
6. repeat with the updated state until the iteration cap, and terminate
   with an explicit mapped stopping reason.

The controller owns no evaluation logic of its own. Selection,
execution, and interpretation are delegated wholesale to the frozen
milestones; ``DiagnosticState`` remains the single authoritative state
(the controller keeps no shadow copy); the baseline artefact is read,
never duplicated or mutated; the target agent is driven only inside
E2-B through ``invoke_act``.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from evaluation.baseline.results import BaselineResult
from evaluation.contracts.agent import validate_target_agent
from evaluation.contracts.stopping import StoppingReason
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.proposals import DiagnosticProposal
from evaluation.diagnostics.execution.episode import DiagnosticEpisodeConfig
from evaluation.diagnostics.execution.executor import execute
from evaluation.diagnostics.interpretation.interpreter import interpret
from evaluation.diagnostics.orchestration.config import OrchestrationConfig
from evaluation.diagnostics.orchestration.results import OrchestrationResult
from evaluation.diagnostics.orchestration.stopping import (
    METHOD,
    TERMINAL_MAPPING,
    VERSION,
)
from evaluation.diagnostics.orchestration.trace import IterationTraceEntry
from evaluation.diagnostics.selection.results import NoCandidateResult
from evaluation.diagnostics.selection.selector import select_next_test


def _check_inputs(
    diagnostic_state: Any,
    baseline: Any,
    target_agent: Any,
    config: Any,
) -> Tuple[DiagnosticState, BaselineResult, Any, OrchestrationConfig]:
    if not isinstance(diagnostic_state, DiagnosticState):
        raise TypeError(
            "diagnostic_state must be a DiagnosticState, "
            f"got {type(diagnostic_state).__name__}"
        )
    if not isinstance(baseline, BaselineResult):
        raise TypeError(
            "baseline must be a BaselineResult, "
            f"got {type(baseline).__name__}"
        )
    if not isinstance(config, OrchestrationConfig):
        raise TypeError(
            "config must be an OrchestrationConfig, "
            f"got {type(config).__name__}"
        )
    agent_errors = validate_target_agent(target_agent)
    if agent_errors:
        raise TypeError(f"invalid target agent: {agent_errors}")
    identity = target_agent.identity
    if (
        identity.agent_id != config.agent_id
        or identity.version != config.agent_version
    ):
        raise ValueError(
            "config agent identity "
            f"({config.agent_id}@{config.agent_version}) does not match "
            f"target agent ({identity.agent_id}@{identity.version})"
        )
    if config.diagnostic_id != diagnostic_state.diagnostic_id:
        raise ValueError(
            "config diagnostic_id does not match diagnostic state"
        )
    if (
        config.baseline_evaluation_id != diagnostic_state.baseline_evaluation_id
        or config.baseline_fingerprint != diagnostic_state.baseline_fingerprint
        or baseline.evaluation_id != diagnostic_state.baseline_evaluation_id
        or baseline.fingerprint() != diagnostic_state.baseline_fingerprint
    ):
        raise ValueError(
            "baseline identity mismatch between config, diagnostic state, "
            "and baseline artefact: refusing to compare against a foreign "
            "control"
        )
    if diagnostic_state.stopping_reason is not None:
        raise ValueError(
            "diagnostic state already carries a stopping reason; "
            "a run starts from an unstopped state"
        )
    return diagnostic_state, baseline, target_agent, config


def _episode_scope(
    baseline: BaselineResult, config: OrchestrationConfig, seed: int
) -> DiagnosticEpisodeConfig:
    if config.window is not None:
        start_date, end_date = config.window
    else:
        start_date = baseline.config.start_date
        end_date = baseline.config.end_date
    universe = (
        dict(config.universe)
        if config.universe is not None
        else dict(baseline.config.universe)
    )
    return DiagnosticEpisodeConfig(
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        seed=seed,
        base_dir=config.base_dir,
    )


def _terminate(
    *,
    diagnostic_state: DiagnosticState,
    baseline: BaselineResult,
    config: OrchestrationConfig,
    iterations: List[IterationTraceEntry],
    terminal_condition: str,
    stopping: StoppingReason,
    no_candidate_reason: Optional[str],
) -> OrchestrationResult:
    diagnostic_state.set_stopping_reason(stopping)
    return OrchestrationResult(
        diagnostic_id=config.diagnostic_id,
        baseline_evaluation_id=config.baseline_evaluation_id,
        baseline_fingerprint=config.baseline_fingerprint,
        config_fingerprint=config.fingerprint(),
        iterations=tuple(iterations),
        terminal_condition=terminal_condition,
        stopping_reason=stopping,
        no_candidate_reason=no_candidate_reason,
        final_state_fingerprint=diagnostic_state.fingerprint(),
        method=METHOD,
        version=VERSION,
    )


def _no_candidate_stopping(outcome: NoCandidateResult) -> StoppingReason:
    if outcome.suggested_stopping is not None:
        return outcome.suggested_stopping
    return TERMINAL_MAPPING["unresolved"]


def run(
    *,
    diagnostic_state: DiagnosticState,
    baseline: BaselineResult,
    target_agent: Any,
    config: OrchestrationConfig,
) -> OrchestrationResult:
    """Run one deterministic closed-loop diagnostic orchestration."""
    diagnostic_state, baseline, target_agent, config = _check_inputs(
        diagnostic_state, baseline, target_agent, config
    )
    iterations: List[IterationTraceEntry] = []
    index = 0
    while index < config.max_iterations:
        if diagnostic_state.stopping_reason is not None:
            return _terminate(
                diagnostic_state=diagnostic_state,
                baseline=baseline,
                config=config,
                iterations=iterations,
                terminal_condition="already_stopped",
                stopping=diagnostic_state.stopping_reason,
                no_candidate_reason=None,
            )
        pre_fp = diagnostic_state.fingerprint()
        outcome = select_next_test(diagnostic_state)
        if isinstance(outcome, NoCandidateResult):
            stopping = _no_candidate_stopping(outcome)
            return _terminate(
                diagnostic_state=diagnostic_state,
                baseline=baseline,
                config=config,
                iterations=iterations,
                terminal_condition="no_candidate",
                stopping=stopping,
                no_candidate_reason=outcome.reason,
            )
        proposal: DiagnosticProposal = outcome
        episode = execute(
            diagnostic_state=diagnostic_state,
            test_id=proposal.selected_test_id,
            prediction_ids=proposal.prediction_ids,
            target_agent=target_agent,
            episode_config=_episode_scope(
                baseline, config, config.seed + index
            ),
        )
        result = episode.result
        if result.status.value != "COMPLETED":
            iterations.append(
                IterationTraceEntry(
                    iteration_index=index,
                    proposal_id=proposal.proposal_id,
                    rationale_id=proposal.rationale_id,
                    test_id=proposal.selected_test_id,
                    result_id=result.result_id,
                    episode_id=episode.episode_id,
                    execution_fingerprint=result.execution_fingerprint,
                    interpretation_id=None,
                    update_ids=(),
                    uncertainty_id=None,
                    pre_state_fingerprint=pre_fp,
                    post_state_fingerprint=diagnostic_state.fingerprint(),
                    completed=False,
                )
            )
            index += 1
            continue
        record = interpret(
            diagnostic_state=diagnostic_state,
            result_id=result.result_id,
            prediction_ids=list(proposal.prediction_ids),
            baseline=baseline,
        )
        uncertainty = diagnostic_state.uncertainty
        iterations.append(
            IterationTraceEntry(
                iteration_index=index,
                proposal_id=proposal.proposal_id,
                rationale_id=proposal.rationale_id,
                test_id=proposal.selected_test_id,
                result_id=result.result_id,
                episode_id=episode.episode_id,
                execution_fingerprint=result.execution_fingerprint,
                interpretation_id=record.interpretation_id,
                update_ids=tuple(record.update_ids),
                uncertainty_id=(
                    uncertainty.assessment_id
                    if uncertainty is not None
                    else None
                ),
                pre_state_fingerprint=pre_fp,
                post_state_fingerprint=diagnostic_state.fingerprint(),
                completed=True,
            )
        )
        index += 1
    return _terminate(
        diagnostic_state=diagnostic_state,
        baseline=baseline,
        config=config,
        iterations=iterations,
        terminal_condition="iteration_cap",
        stopping=TERMINAL_MAPPING["iteration_cap"],
        no_candidate_reason=None,
    )
