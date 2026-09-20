"""E3-E execution lifecycle, Phases A–E (orchestration only, no science).

Phase A executes N-D and N-H on fresh original-agent instances, seals
N-H, and discards execution objects so only the seal survives. Phase B
diagnoses through ONE shared executor with a policy seam (manifest
order vs frozen E2-D selector) over shared execute → interpret →
record calls. Phase C is a single frozen ``run_repair`` call (repair +
validation + ledger owned by E2-F). Phase D evaluates R-D/R-H under
lineage guards. Phase E verifies the seal, releases once, builds
paired deltas, and assembles the immutable result.

Prediction content is transcribed verbatim from frozen E3-C §9
(``FROZEN_PREDICTION_MATRIX``); test descriptors from the frozen
manifest pool plus fixed E3-C wording (``TEST_SPECS``). Transcription,
not science: any mismatch with E3-C fails at review, never at runtime
by invention.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, List, Mapping, Optional, Tuple

from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.results import BaselineResult
from evaluation.baseline.runner import run_baseline
from evaluation.contracts.agent import AgentIdentity, validate_target_agent
from evaluation.contracts.budget import EvaluationBudget
from evaluation.contracts.diagnostic_tests import DiagnosticTest
from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.contracts.hypotheses import Hypothesis
from evaluation.contracts.hypotheses import Hypothesis
from evaluation.diagnostics.contracts.diagnostic_state import DiagnosticState
from evaluation.diagnostics.contracts.predictions import (
    ExpectedDirection,
    HypothesisPrediction,
)
from evaluation.diagnostics.execution.episode import DiagnosticEpisodeConfig
from evaluation.diagnostics.execution.executor import execute
from evaluation.diagnostics.interpretation.interpreter import interpret
from evaluation.diagnostics.repair.results import run_repair
from evaluation.diagnostics.selection.results import NoCandidateResult
from evaluation.diagnostics.selection.selector import select_next_test
from experiments.harness import lineage as lineage_mod
from experiments.harness.config import ExperimentConfig
from experiments.harness.errors import (
    IntegrityFailure,
    LineageError,
    ProtocolAmbiguityError,
)
from experiments.harness.identity import experiment_identity
from experiments.harness.lineage import (
    ASSEMBLY_PHASE,
    SealedBaseline,
    assert_same_scope,
    assert_transition,
    heldout_scope,
    require_repair_lineage,
    require_rh_lineage,
)
from experiments.harness.result import ExperimentResult

# Transcribed from frozen E3-C §9 (prediction matrix, H-turnover only).
# (hypothesis_id, test_id) -> (observable, direction, rationale).
FROZEN_PREDICTION_MATRIX: Tuple[Tuple[str, str, str, str, str], ...] = (
    ("H-turnover", "T-null", "turnover", "NO_CHANGE", "null control"),
    (
        "H-turnover", "T-cost2x", "transaction_cost_total", "INCREASE",
        "doubled costs raise cost totals",
    ),
    (
        "H-turnover", "T-cost0", "transaction_cost_total", "DECREASE",
        "zeroed costs lower cost totals",
    ),
    (
        "H-turnover", "T-vintage-earliest", "turnover", "NO_CHANGE",
        "vintage resolution does not move order flow",
    ),
    (
        "H-turnover", "T-uni-tcs", "turnover", "DECREASE",
        "fewer names to accumulate, less order flow",
    ),
)

# Test descriptors for manifest pool ids (fixed E3-C wording).
TEST_SPECS: Dict[str, Dict[str, Any]] = {
    "T-null": {
        "description": "null-intervention control",
        "target_failure_classes": ("turnover",),
        "expected_discrimination": "control; no mechanism movement expected",
    },
    "T-cost2x": {
        "description": "double transaction costs",
        "target_failure_classes": ("turnover",),
        "expected_discrimination": "cost-total response probe",
    },
    "T-cost0": {
        "description": "zero transaction costs",
        "target_failure_classes": ("turnover",),
        "expected_discrimination": "cost-total response probe",
    },
    "T-vintage-earliest": {
        "description": "earliest-available vintage resolution",
        "target_failure_classes": ("turnover",),
        "expected_discrimination": "information-policy sensitivity probe",
    },
    "T-uni-tcs": {
        "description": "restrict universe to TCS:EQ",
        "target_failure_classes": ("turnover",),
        "expected_discrimination": "order-flow restriction probe",
    },
}


def instantiate_agent(benchmark_module: str) -> Any:
    """Construct one fresh benchmark-agent instance (no shared state)."""
    if not isinstance(benchmark_module, str) or not benchmark_module.strip():
        raise ValueError("benchmark_module must be a non-empty string")
    module_name, _, class_name = benchmark_module.rpartition(".")
    if not module_name or not class_name:
        raise ValueError(
            "benchmark_module must be a dotted path 'package.module.Class'"
        )
    agent_class = getattr(import_module(module_name), class_name)
    agent = agent_class()
    errors = validate_target_agent(agent)
    if errors:
        raise IntegrityFailure(f"benchmark agent invalid: {errors}")
    return agent


def baseline_config_for(
    config: ExperimentConfig, window: Tuple[str, str], evaluation_id: str,
    max_episodes: int = 1,
) -> BaselineConfig:
    """Build a frozen BaselineConfig for one window (pure, no episodes)."""
    return BaselineConfig(
        evaluation_id=evaluation_id,
        start_date=window[0],
        end_date=window[1],
        universe=dict(config.universe),
        transaction_cost_bps=config.transaction_cost_bps,
        initial_cash=config.initial_cash,
        strict_pit=config.strict_pit,
        vintage_policy=config.vintage_policy,
        budget=EvaluationBudget(
            max_episodes=max_episodes,
            max_tests=None,
            max_repairs=None,
            max_validation_runs=None,
            max_runtime=None,
        ),
        seed=config.seed_provenance,
    )


def diagnostic_state_for(
    config: ExperimentConfig,
    baseline: BaselineResult,
    agent_identity: AgentIdentity,
    diagnostic_id: str,
) -> DiagnosticState:
    """Build a fresh DiagnosticState bound to one baseline (pure)."""
    return DiagnosticState(
        diagnostic_id=diagnostic_id,
        baseline_evaluation_id=baseline.evaluation_id,
        baseline_fingerprint=baseline.fingerprint(),
        agent_identity=agent_identity,
        environment_spec=dict(baseline.environment_spec),
        config={},
        budget=EvaluationBudget(
            max_episodes=None,
            max_tests=int(dict(config.budgets)["max_tests"]),
            max_repairs=None,
            max_validation_runs=None,
            max_runtime=None,
        ),
    )


def paired_deltas(
    reference_metrics: Mapping[str, Any],
    validation_metrics: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Paired per-metric differences preserving None (no imputation).

    Each entry carries reference/validation/delta where delta is None
    unless both sides are finite numbers. Missing keys are reported,
    never filled.
    """
    deltas: Dict[str, Dict[str, Any]] = {}
    for name in sorted(set(reference_metrics) | set(validation_metrics)):
        reference = reference_metrics.get(name)
        validation = validation_metrics.get(name)
        delta = None
        if (
            isinstance(reference, (int, float))
            and not isinstance(reference, bool)
            and isinstance(validation, (int, float))
            and not isinstance(validation, bool)
        ):
            delta = float(validation) - float(reference)
        deltas[str(name)] = {
            "reference": reference,
            "validation": validation,
            "delta": delta,
        }
    return deltas


def metric_map(baseline: BaselineResult) -> Dict[str, Any]:
    """Plain metric name → value map from a baseline artefact."""
    if not isinstance(baseline, BaselineResult):
        raise TypeError(
            "baseline must be a BaselineResult, "
            f"got {type(baseline).__name__}"
        )
    return {metric.name: metric.value for metric in baseline.metrics}


def build_prediction_matrix() -> Tuple[Tuple[str, str, str, str, str], ...]:
    """Return the frozen prediction matrix (transcription accessor)."""
    return FROZEN_PREDICTION_MATRIX


def verify_transcription(manifest: Mapping[str, Any]) -> None:
    """Fail closed unless the harness transcription matches frozen sources.

    Pure and side-effect-free. Checks the transcribed prediction matrix
    and test descriptors against the frozen E3-C manifest (hypothesis
    ids, candidate pool) and the frozen E1 metric inventory
    (observable names). Per-test directions are type-checked as
    ``ExpectedDirection`` members at commit time; the manifest carries
    no per-test direction table, so direction *values* are pinned by
    the E3-C protocol document and covered by review, not by this
    check. Must run before any executable identity is derived.
    """
    from evaluation.baseline.metrics import METRIC_FUNCTIONS

    if not isinstance(manifest, Mapping):
        raise TypeError("manifest must be a mapping")
    manifest_hypotheses = manifest.get("hypotheses", [])
    if len(manifest_hypotheses) != 1:
        raise ProtocolAmbiguityError(
            "E3-C.2 freezes exactly one active hypothesis; manifest "
            f"declares {len(manifest_hypotheses)}: refusing to choose"
        )
    manifest_hyp_ids = {
        entry["hypothesis_id"] for entry in manifest_hypotheses
    }
    pool_ids = {
        entry["test_id"] for entry in manifest.get("candidate_pool", [])
    }
    if not pool_ids:
        raise ProtocolAmbiguityError(
            "manifest declares an empty candidate pool"
        )
    metric_names = {function.__name__ for function in METRIC_FUNCTIONS}
    for hypothesis_id, test_id, observable, direction, _ in (
        FROZEN_PREDICTION_MATRIX
    ):
        if hypothesis_id not in manifest_hyp_ids:
            raise ProtocolAmbiguityError(
                f"transcribed hypothesis {hypothesis_id!r} not in "
                f"manifest {sorted(manifest_hyp_ids)}"
            )
        if test_id not in pool_ids:
            raise ProtocolAmbiguityError(
                f"transcribed test {test_id!r} not in manifest pool"
            )
        if observable not in metric_names:
            raise ProtocolAmbiguityError(
                f"transcribed observable {observable!r} is not a frozen "
                "E1 metric"
            )
        ExpectedDirection.from_str(direction)
    if set(TEST_SPECS) != pool_ids:
        raise ProtocolAmbiguityError(
            "transcribed test descriptors do not exactly match the "
            f"manifest pool: specs={sorted(TEST_SPECS)} "
            f"pool={sorted(pool_ids)}"
        )


def commit_predictions(
    state: DiagnosticState, hypothesis_id: str
) -> None:
    """Commit frozen-matrix predictions for one hypothesis (pure record)."""
    rows = [
        row for row in FROZEN_PREDICTION_MATRIX if row[0] == hypothesis_id
    ]
    if not rows:
        raise ProtocolAmbiguityError(
            f"no frozen predictions for hypothesis {hypothesis_id!r}: "
            "refusing to invent prediction directions at runtime"
        )
    for hypothesis_id_, test_id, observable, direction, rationale in rows:
        state.record_prediction(
            HypothesisPrediction(
                prediction_id=(
                    f"{state.diagnostic_id}-pred-"
                    f"{hypothesis_id_}-{test_id}"
                ),
                hypothesis_id=hypothesis_id_,
                test_id=test_id,
                predicted_observable=observable,
                expected_direction=ExpectedDirection.from_str(direction),
                rationale=rationale,
                derivation_method="E3-C-spec",
                derivation_version="2",
            )
        )


def register_pool_tests(
    state: DiagnosticState,
    pool: Mapping[str, Mapping[str, Any]],
) -> None:
    """Register manifest pool tests with frozen descriptors (pure record)."""
    for test_id in sorted(pool):
        spec = TEST_SPECS.get(test_id)
        if spec is None:
            raise ProtocolAmbiguityError(
                f"no frozen descriptor for candidate test {test_id!r}: "
                "refusing to describe tests at runtime"
            )
        entry = pool[test_id]
        state.register_test(
            DiagnosticTest(
                test_id=test_id,
                description=str(spec["description"]),
                target_failure_classes=tuple(
                    spec["target_failure_classes"]
                ),
                intervention=dict(entry["intervention"]),
                measures=tuple(entry["measures"]),
                expected_discrimination=str(
                    spec["expected_discrimination"]
                ),
                estimated_cost=float(entry["estimated_cost"]),
            )
        )


def diagnose(
    *,
    state: DiagnosticState,
    baseline: BaselineResult,
    target_agent: Any,
    policy: str,
    fixed_sequence: Tuple[str, ...],
    seed: Optional[int],
    base_dir: str = ".",
) -> Dict[str, Any]:
    """Run one diagnostic episode through the shared executor path.

    Policy seam: ``fixed`` pops manifest order; ``adaptive`` asks the
    frozen E2-D selector. Everything after selection — execute,
    interpret, record — is the identical shared path. Returns a trace
    summary (completed tests, stopping condition, fingerprints).
    """
    if policy not in ("fixed", "adaptive"):
        raise ValueError(
            f"policy must be 'fixed' or 'adaptive', got {policy!r}"
        )
    remaining = [t for t in fixed_sequence]
    completed: List[str] = []
    invalid: List[str] = []
    index = 0
    while True:
        if policy == "fixed":
            pending = [t for t in remaining if t not in completed + invalid]
            if not pending:
                stopping = "sequence_exhausted"
                break
            test_id = pending[0]
            prediction_ids = [
                p.prediction_id
                for p in state.predictions
                if p.test_id == test_id
            ]
        else:
            outcome = select_next_test(state)
            if isinstance(outcome, NoCandidateResult):
                stopping = f"no_candidate:{outcome.reason}"
                break
            test_id = outcome.selected_test_id
            prediction_ids = list(outcome.prediction_ids)
        episode = execute(
            diagnostic_state=state,
            test_id=test_id,
            prediction_ids=prediction_ids,
            target_agent=target_agent,
            episode_config=DiagnosticEpisodeConfig(
                start_date=str(baseline.config.start_date),
                end_date=str(baseline.config.end_date),
                universe=dict(baseline.config.universe),
                seed=int(seed or 0) + index,
                base_dir=base_dir,
            ),
        )
        result = episode.result
        if result.status.value != "COMPLETED":
            invalid.append(test_id)
            if policy == "fixed":
                # Manifest F semantics: INVALID records and continues,
                # FAILED records and halts.
                if result.status.value == "FAILED":
                    stopping = f"failed:{test_id}"
                    break
                index += 1
                continue
            index += 1
            continue
        interpret(
            diagnostic_state=state,
            result_id=result.result_id,
            prediction_ids=list(prediction_ids),
            baseline=baseline,
        )
        completed.append(test_id)
        index += 1
        if state.budget.is_exhausted(state.budget_usage()):
            stopping = "budget_exhausted"
            break
    return {
        "policy": policy,
        "completed": completed,
        "invalid_or_failed": invalid,
        "stopping": stopping,
        "state_fingerprint": state.fingerprint(),
    }


def _fresh_agent(config: ExperimentConfig) -> Any:
    """One fresh legitimate agent instance per arm (isolation)."""
    return instantiate_agent(config.benchmark_module)


def phase_a(
    config: ExperimentConfig, experiment_id: str, base_dir: str = "."
) -> Tuple[BaselineResult, SealedBaseline]:
    """Execute N-D and sealed N-H on isolated fresh instances."""
    agent_nd = _fresh_agent(config)
    agent_nd.reset()
    baseline_nd = run_baseline(
        agent_nd,
        baseline_config_for(
            config, config.diagnostic_window,
            f"{experiment_id}-N-D",
        ),
        base_dir=base_dir,
    )
    del agent_nd
    agent_nh = _fresh_agent(config)
    agent_nh.reset()
    baseline_nh = run_baseline(
        agent_nh,
        baseline_config_for(
            config, config.heldout_window, f"{experiment_id}-N-H"
        ),
        base_dir=base_dir,
    )
    del agent_nh
    scope = heldout_scope(
        heldout_window=config.heldout_window,
        universe=dict(config.universe),
        transaction_cost_bps=config.transaction_cost_bps,
        initial_cash=config.initial_cash,
        strict_pit=config.strict_pit,
        vintage_policy=config.vintage_policy,
        environment_fingerprint=config.environment_fingerprint,
    )
    sealed = SealedBaseline.seal(payload=baseline_nh, scope=scope)
    del baseline_nh
    return baseline_nd, sealed


def _diagnose_with_agent(
    *,
    config: ExperimentConfig,
    baseline_nd: BaselineResult,
    manifest: Mapping[str, Any],
    agent: Any,
    base_dir: str,
) -> Tuple[DiagnosticState, Dict[str, Any]]:
    """Shared diagnostic body for an explicitly owned agent instance."""
    state = diagnostic_state_for(
        config,
        baseline_nd,
        agent.identity,
        f"{config.arm}-D",
    )
    hypotheses = manifest.get("hypotheses", [])
    if not hypotheses:
        raise ProtocolAmbiguityError(
            "manifest declares no hypotheses: refusing to choose "
            "a diagnostic target at runtime"
        )
    for entry in hypotheses:
        state.register_hypothesis(
            Hypothesis(
                hypothesis_id=entry["hypothesis_id"],
                failure_class=entry["failure_class"],
                mechanism=entry["mechanism"],
                confidence=0.5,
                evidence_refs=("E3-C:manifest",),
            )
        )
    pool = {
        entry["test_id"]: entry
        for entry in manifest.get("candidate_pool", [])
    }
    register_pool_tests(state, pool)
    for entry in hypotheses:
        commit_predictions(state, entry["hypothesis_id"])
    trace = diagnose(
        state=state,
        baseline=baseline_nd,
        target_agent=agent,
        policy=config.diagnostic_policy,
        fixed_sequence=config.fixed_sequence,
        seed=config.seed_provenance,
        base_dir=base_dir,
    )
    return state, trace


def phase_b(
    config: ExperimentConfig,
    baseline_nd: BaselineResult,
    manifest: Mapping[str, Any],
    base_dir: str = ".",
) -> Tuple[DiagnosticState, Dict[str, Any]]:
    """Diagnose under the configured policy. Sealed N-H never arrives."""
    agent = _fresh_agent(config)
    try:
        return _diagnose_with_agent(
            config=config,
            baseline_nd=baseline_nd,
            manifest=manifest,
            agent=agent,
            base_dir=base_dir,
        )
    finally:
        del agent


def phase_c(
    diagnostic_state: DiagnosticState,
    baseline_nd: BaselineResult,
    original_agent: Any,
    hypothesis_id: str,
    heldout_window: Tuple[str, str],
    seed: Optional[int],
    base_dir: str = ".",
):
    """Repair + validation via one frozen run_repair call (E2-F owns it)."""
    return run_repair(
        diagnostic_state=diagnostic_state,
        baseline=baseline_nd,
        original_agent=original_agent,
        hypothesis_id=hypothesis_id,
        heldout_window=heldout_window,
        seed=seed,
        base_dir=base_dir,
    )


def phase_d_rd(
    config: ExperimentConfig,
    experiment_id: str,
    live_candidate: Any,
    repair_decision: str,
    validation_fingerprint: str,
    base_dir: str = ".",
) -> BaselineResult:
    """Evaluate the repaired agent on the diagnostic window (guarded)."""
    require_repair_lineage(repair_decision, validation_fingerprint)
    return run_baseline(
        live_candidate,
        baseline_config_for(
            config, config.diagnostic_window, f"{experiment_id}-R-D"
        ),
        base_dir=base_dir,
    )


def phase_d_rh(
    config: ExperimentConfig,
    experiment_id: str,
    live_candidate: Any,
    repaired_identity: str,
    repair_fingerprint: str,
    sealed_nh: SealedBaseline,
    base_dir: str = ".",
) -> BaselineResult:
    """Evaluate the repaired agent on the held-out window (guarded)."""
    require_rh_lineage(repaired_identity, repair_fingerprint)
    scope = heldout_scope(
        heldout_window=config.heldout_window,
        universe=dict(config.universe),
        transaction_cost_bps=config.transaction_cost_bps,
        initial_cash=config.initial_cash,
        strict_pit=config.strict_pit,
        vintage_policy=config.vintage_policy,
        environment_fingerprint=config.environment_fingerprint,
    )
    assert_same_scope(scope, dict(sealed_nh.scope))
    return run_baseline(
        live_candidate,
        baseline_config_for(
            config, config.heldout_window, f"{experiment_id}-R-H"
        ),
        base_dir=base_dir,
    )


def phase_e_assemble(
    *,
    config: ExperimentConfig,
    experiment_id: str,
    baseline_nd: BaselineResult,
    sealed_nh: SealedBaseline,
    diagnostic_state: DiagnosticState,
    diagnostic_trace: Mapping[str, Any],
    repair_result: Any,
    validation_report: Any,
    baseline_rd: BaselineResult,
    baseline_rh: BaselineResult,
    integrity_notes: Optional[Mapping[str, Any]] = None,
) -> ExperimentResult:
    """Verify seal, release once, build deltas, assemble the result."""
    assert_transition("R-H", "ASSEMBLY")
    released = sealed_nh.release(phase=lineage_mod.ASSEMBLY_PHASE)
    baseline_nh = released.contents()
    if baseline_nh.fingerprint() != sealed_nh.baseline_fingerprint:
        raise IntegrityFailure(
            "released N-H fingerprint does not match seal lineage"
        )
    scope_window = tuple(sealed_nh.scope["heldout_window"])
    payload_window = (
        str(baseline_nh.config.start_date),
        str(baseline_nh.config.end_date),
    )
    if payload_window != scope_window:
        raise IntegrityFailure(
            "released N-H window does not match the sealed held-out "
            "scope: N-D must never be substituted for N-H"
        )
    metrics_nd = metric_map(baseline_nd)
    metrics_nh = metric_map(baseline_nh)
    metrics_rd = metric_map(baseline_rd)
    metrics_rh = metric_map(baseline_rh)
    delta_diagnostic = paired_deltas(metrics_nd, metrics_rd)
    delta_heldout = {
        **paired_deltas(metrics_nh, metrics_rh),
        "baseline_original_heldout": baseline_nh.fingerprint(),
        "repaired_heldout": baseline_rh.fingerprint(),
    }
    if (
        delta_heldout["baseline_original_heldout"]
        != sealed_nh.baseline_fingerprint
    ):
        raise IntegrityFailure(
            "RQ3 comparator is not the sealed N-H baseline: failing closed"
        )
    trace = dict(diagnostic_trace)
    lineage = {
        "experiment_id": experiment_id,
        "baseline_nd": baseline_nd.fingerprint(),
        "baseline_nh_seal": sealed_nh.seal_fingerprint,
        "diagnostic_state": diagnostic_state.fingerprint(),
        "repair": repair_result.fingerprint(),
        "validation": validation_report.fingerprint(),
        "baseline_rd": baseline_rd.fingerprint(),
        "baseline_rh": baseline_rh.fingerprint(),
    }
    stopping = diagnostic_state.stopping_reason
    rq4_vector = {
        "tests_consumed": len(trace.get("completed", []))
        + len(trace.get("invalid_or_failed", [])),
        "terminal_state": (
            stopping.value if stopping is not None else None
        ),
        "state_fingerprint": trace.get("state_fingerprint"),
    }
    return ExperimentResult(
        experiment_id=experiment_id,
        protocol_fingerprint=config.e3d_fingerprint,
        arm_records={
            "arm": config.arm,
            "diagnostic_policy": config.diagnostic_policy,
            "diagnostic_trace": trace,
        },
        benchmark_identity={
            "benchmark_id": config.benchmark_id,
            "benchmark_version": config.benchmark_version,
        },
        agent_identity={
            "agent_id": config.agent_id,
            "agent_version": config.agent_version,
        },
        environment_identity={
            "environment_fingerprint": config.environment_fingerprint,
            "calendar_fingerprint": config.calendar_fingerprint,
            "dataset_fingerprints": dict(config.dataset_fingerprints),
        },
        configuration=config.to_dict(),
        lineage=lineage,
        metrics_nd=metrics_nd,
        metrics_nh=metrics_nh,
        metrics_rd=metrics_rd,
        metrics_rh=metrics_rh,
        delta_diagnostic=delta_diagnostic,
        delta_heldout=delta_heldout,
        rq4_vector=rq4_vector,
        result_state="INCONCLUSIVE",
        failure_detail="assembled; Tier-1 analysis belongs downstream",
        integrity_checks=dict(integrity_notes or {}),
        operational={},
    )


def campaign_experiment_id(config: ExperimentConfig) -> str:
    """Identity helper shared by lifecycle entry points."""
    return experiment_identity(config)


def run_experiment(
    *,
    config: ExperimentConfig,
    manifest: Mapping[str, Any],
    e3d_document_path: str,
    environment_fingerprint: str,
    benchmark_fingerprint: str,
    agent_fingerprint: str,
    base_dir: str = ".",
) -> ExperimentResult:
    """Execute one canonical Tier-1 campaign: preflight, A→B→C→D→E.

    The single orchestration entrypoint. Verifies configuration,
    transcription, and preflight before deriving identity; executes
    phases in order with no skips; persists the final result and
    returns it. Fail-closed throughout; invents no science.
    """
    from experiments.harness.identity import result_path
    from experiments.harness.preflight import ensure_preflight, preflight

    config.verify_against_manifest(manifest)
    verify_transcription(manifest)
    report = preflight(
        config=config,
        manifest=manifest,
        e3d_document_path=e3d_document_path,
        environment_fingerprint=environment_fingerprint,
        benchmark_fingerprint=benchmark_fingerprint,
        agent_fingerprint=agent_fingerprint,
    )
    ensure_preflight(report)
    experiment_id = experiment_identity(config)

    # Phase A: original baselines; N-H sealed, execution objects dropped.
    assert_transition("N-D", "D-F" if config.diagnostic_policy == "fixed" else "D-A")
    baseline_nd, sealed_nh = phase_a(config, experiment_id, base_dir)
    assert_transition("N-H", "SEALED")

    # Phase B: diagnosis on an explicitly owned fresh agent instance.
    # The instance is discarded afterwards and never reused for repair.
    agent_diag = _fresh_agent(config)
    agent_diag.reset()
    try:
        diagnostic_state, trace = _diagnose_with_agent(
            config=config,
            baseline_nd=baseline_nd,
            manifest=manifest,
            agent=agent_diag,
            base_dir=base_dir,
        )
    finally:
        del agent_diag
    assert_transition(
        "D-F" if config.diagnostic_policy == "fixed" else "D-A", "REPAIR"
    )

    # Phase C: exactly one frozen run_repair on a fresh equivalent agent.
    # Legitimacy is determinism + reset-state equivalence, not object
    # identity: same canonical benchmark identity/version/config, reset
    # before use. E2-F remains sole budget owner.
    agent_repair = _fresh_agent(config)
    agent_repair.reset()
    try:
        hypothesis_id = str(manifest["hypotheses"][0]["hypothesis_id"])
        repair_result, validation_report, _analysis, live_candidate = (
            phase_c(
                diagnostic_state,
                baseline_nd,
                agent_repair,
                hypothesis_id,
                tuple(config.heldout_window),
                config.seed_provenance,
                base_dir,
            )
        )
    finally:
        del agent_repair
    assert_transition("REPAIR", "R-D")

    # Phase D: guarded repaired evaluations.
    decision = repair_result.decision
    decision_value = decision.value if hasattr(decision, "value") else str(
        decision
    )
    baseline_rd = phase_d_rd(
        config,
        experiment_id,
        live_candidate,
        decision_value,
        repair_result.validation_fingerprint,
        base_dir,
    )
    assert_transition("R-D", "R-H")
    baseline_rh = phase_d_rh(
        config,
        experiment_id,
        live_candidate,
        repair_result.candidate_id,
        repair_result.fingerprint(),
        sealed_nh,
        base_dir,
    )
    assert_transition("R-H", "ASSEMBLY")

    # Phase E: verify seal, release once, assemble, persist, return.
    result = phase_e_assemble(
        config=config,
        experiment_id=experiment_id,
        baseline_nd=baseline_nd,
        sealed_nh=sealed_nh,
        diagnostic_state=diagnostic_state,
        diagnostic_trace=trace,
        repair_result=repair_result,
        validation_report=validation_report,
        baseline_rd=baseline_rd,
        baseline_rh=baseline_rh,
        integrity_notes={
            "preflight_experiment_id": report.experiment_id,
            "entrypoint": "run_experiment",
        },
    )
    result.save(result_path(config.result_dir, experiment_id))
    return result
