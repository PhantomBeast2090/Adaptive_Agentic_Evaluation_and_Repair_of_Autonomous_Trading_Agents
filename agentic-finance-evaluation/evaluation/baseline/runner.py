"""Deterministic baseline evaluation runner (E1).

:func:`run_baseline` connects the frozen pieces without reimplementing any
of them::

    IndianMultiAssetEnvironment (existing, untouched)
        -> trusted EnvironmentState (trusted.observe_current)
        -> TargetObservation (E0 trusted path)
        -> TargetAgent via E0 invoke_act
        -> order list submitted to env.step (environment executes)
        -> DecisionRecord per decision (actuals only)
        -> deterministic metrics + BehavioralEvidence
        -> EvaluationState + BaselineResult

The runner owns no market logic, no metric math beyond orchestration, and
no diagnosis. A malformed agent or exhausted budget fails closed before or
during the run; a completed window maps to ``NO_ACTIONABLE_FAILURE`` (E1 is
measurement-only and raises nothing actionable — documented in
``docs/BASELINE_EVALUATOR.md``, not a claim about the agent).

One completed ``run_baseline`` over one window consumes exactly one E0
episode (D5). ``max_runtime`` is not wall-clock enforced (documented).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from environment.indian.actions import validate_orders
from environment.indian.environment import IndianMultiAssetEnvironment
from evaluation.baseline.config import BaselineConfig
from evaluation.baseline.evidence import derive_baseline_evidence
from evaluation.baseline.metrics import compute_all
from evaluation.baseline.results import BaselineResult
from evaluation.baseline.trusted import (
    observation_portfolio,
    observe_current,
    split_visibility,
)
from evaluation.contracts.agent import invoke_act, validate_target_agent
from evaluation.contracts.decision_record import DecisionRecord
from evaluation.contracts.evaluation_state import EvaluationState
from evaluation.contracts.oracle import TargetObservation
from evaluation.contracts.stopping import StoppingReason


def _validation_entries(orders: List[Dict[str, Any]], env: Any) -> List[Dict[str, Any]]:
    """Record pre-execution validation with the environment's own validator.

    The environment remains the sole execution authority; reusing its
    public ``validate_orders`` with its configured universe reproduces the
    identical validation deterministically for the record. Entries are
    sorted by the same key the environment uses so validation rows align
    with execution rows.
    """
    validated = validate_orders(orders, env.allowed_instruments)
    validated.sort(key=lambda order: (order.asset_id, order.instrument))
    return [
        {
            "status": item.status,
            "asset_id": item.asset_id,
            "instrument": item.instrument,
            "side": item.side,
            "requested_quantity": item.requested_quantity,
            "constraint_binding": item.constraint_binding,
            "detail": item.detail,
        }
        for item in validated
    ]


def _build_record(
    observation: TargetObservation,
    orders: List[Dict[str, Any]],
    validation: List[Dict[str, Any]],
    info: Dict[str, Any],
    session_index: int,
    market_fingerprint: str,
    termination_reason: str,
    finished: bool,
) -> DecisionRecord:
    before = observation_portfolio(observation)
    after_total = float(info["portfolio_value"])
    after_cash = float(info["cash"])
    executions = copy.deepcopy(list(info["executions"]))
    return DecisionRecord(
        decision_timestamp=observation.decision_timestamp,
        state_fingerprint=observation.fingerprint(),
        visible_assets=split_visibility(observation)[0],
        unavailable_assets=split_visibility(observation)[1],
        # Semantic content preserved, agent-owned objects never retained:
        # DecisionRecord deep-freezes everything at construction.
        submitted_orders=copy.deepcopy([dict(order) for order in orders]),
        validation=copy.deepcopy(validation),
        executions=executions,
        execution_price=(
            float(info["execution_price"]) if executions else None
        ),
        transaction_cost=float(info["transaction_costs"]),
        portfolio_before=before,
        portfolio_after={
            "cash": after_cash,
            "total_equity": after_total,
            "holdings_value": after_total - after_cash,
            "positions": copy.deepcopy(dict(info["positions"])),
            "exposure": (
                (after_total - after_cash) / after_total
                if after_total > 0
                else 0.0
            ),
        },
        # Exactly the environment's number: portfolio-value change incl.
        # costs. DecisionRecord enforces after-minus-before equality.
        reward=float(info["step_pnl"]),
        environment_metadata={
            "market_fingerprint": market_fingerprint,
            "session_index": session_index,
            "done": finished,
            "termination_reason": termination_reason,
        },
        agent_metadata=None,
    )


def run_baseline(
    agent: Any, config: BaselineConfig, *, base_dir: str = "."
) -> BaselineResult:
    """Run one deterministic baseline evaluation over one window.

    Args:
        agent: a structurally valid target agent (order-list contract).
        config: explicit, validated baseline policy.
        base_dir: repository root for canonical data (passed through to
            the environment; part of provenance, not identity).

    Returns:
        The complete ``BaselineResult`` artefact.

    Raises:
        TypeError: invalid agent, malformed agent output, or wrong config
            type. Never coerced, never substituted.
        ValueError: exhausted episode budget (refused before execution) or
            invalid window (propagated from the environment).
        RuntimeError: the environment fails to terminate within its grid.
    """
    errors = validate_target_agent(agent)
    if errors:
        raise TypeError(f"invalid target agent: {errors}")
    if not isinstance(config, BaselineConfig):
        raise TypeError(
            "config must be a BaselineConfig, "
            f"got {type(config).__name__}"
        )
    if config.budget.is_exhausted({"episodes": 0}):
        raise ValueError(
            "evaluation budget exhausted before execution "
            "(max_episodes=0 allows no runs)"
        )

    env = IndianMultiAssetEnvironment(config.to_env_config(), base_dir=base_dir)
    spec = env.spec()

    agent.reset()
    env.reset()  # lifecycle effect only; observations flow via trusted.py

    records: List[DecisionRecord] = []
    while not env.done:
        if len(records) >= len(env.grid):
            raise RuntimeError(
                "environment did not terminate within its decision grid"
            )
        session_index = env.index
        observation = observe_current(env)
        # invoke_act type-gates the observation and validates the return
        # shape; a broken agent aborts the run loudly (no partial result).
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

    metrics = compute_all(records, config.initial_cash)
    evidence = derive_baseline_evidence(
        config.evaluation_id,
        {metric.name: metric for metric in metrics},
        [record.fingerprint() for record in records],
        {
            "market_fingerprint": spec["market_fingerprint"],
            "config_fingerprint": config.fingerprint(),
            "evaluator": "e1-baseline",
        },
    )
    state = EvaluationState(
        evaluation_id=config.evaluation_id,
        agent_identity=agent.identity,
        environment_spec=spec,
        config=config.to_dict(),
        budget=config.budget,
    )
    for item in evidence:
        state.add_baseline_evidence(item)
    state.set_stopping_reason(StoppingReason.NO_ACTIONABLE_FAILURE)
    return BaselineResult(
        evaluation_id=config.evaluation_id,
        agent_identity=agent.identity,
        environment_spec=spec,
        config=config,
        decision_records=tuple(records),
        metrics=metrics,
        evidence=evidence,
        evaluation_state=state,
        stopping_reason=StoppingReason.NO_ACTIONABLE_FAILURE,
        budget_usage={"episodes": 1},
    )
