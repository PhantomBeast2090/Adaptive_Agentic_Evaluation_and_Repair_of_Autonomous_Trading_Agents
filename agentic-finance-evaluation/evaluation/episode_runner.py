"""Episode execution, separated from evaluation.

`run_episode` drives one agent through one windowed market episode and returns a
`Trajectory`. It computes no metrics and makes no judgements: every evaluation
dimension is derived downstream from the recorded trajectory. Keeping execution
and evaluation apart is what allows the same recorded episode to be re-scored by
different evaluators without re-running the market.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agents.financial_agent.base import BaseTradingAgent
from environment.core import FinancialEnvironment
from src.trace.logger import TraceLogger


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Trajectory:
    """A complete recorded episode.

    Holds everything an evaluator needs plus everything a reader needs to
    reproduce the run: the resolved environment spec (including a fingerprint of
    the replayed market rows), the agent identity, and the recorded seed.
    """

    def __init__(
        self,
        episode_id: str,
        scenario_id: str,
        agent_id: str,
        agent_version: str,
        seed: Optional[int] = None,
        environment_spec: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.episode_id = episode_id
        self.scenario_id = scenario_id
        self.agent_id = agent_id
        self.agent_version = agent_version
        self.seed = seed
        self.environment_spec: Dict[str, Any] = environment_spec or {}
        self.metadata: Dict[str, Any] = metadata or {}
        self.created_at = _utc_now_iso()
        self.steps: List[Dict[str, Any]] = []
        self.initial_state: Optional[Dict[str, Any]] = None
        self.final_state: Optional[Dict[str, Any]] = None

    def add_step(
        self,
        step_index: int,
        date: str,
        observation: Dict[str, Any],
        action: Dict[str, Any],
        outcome: Dict[str, Any],
    ) -> None:
        self.steps.append(
            {
                "step_index": step_index,
                "date": date,
                "observation": observation,
                "action": action,
                "outcome": outcome,
            }
        )

    def __len__(self) -> int:
        return len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "scenario_id": self.scenario_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "seed": self.seed,
            "created_at": self.created_at,
            "environment_spec": self.environment_spec,
            "metadata": self.metadata,
            "initial_state": self.initial_state,
            "final_state": self.final_state,
            "steps": self.steps,
        }

    def content_digest(self) -> str:
        """SHA-256 digest of the reproducible content of this episode.

        Excludes `episode_id` and `created_at`, which carry provenance rather
        than behaviour, and `environment_spec["data_path"]`, which is a
        machine-specific filesystem location: the identity of the replayed
        market rows is already carried by `environment_spec["market_fingerprint"]`.
        Two runs of the same agent on the same scenario must produce the same
        digest, on any checkout; that is the reproducibility check.
        """
        payload = self.to_dict()
        payload.pop("created_at", None)
        payload.pop("episode_id", None)
        spec = dict(payload.get("environment_spec") or {})
        spec.pop("data_path", None)
        payload["environment_spec"] = spec
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_decision(decision: Any) -> Dict[str, Any]:
    """Normalise an agent's returned decision for submission and recording.

    A missing or malformed decision is *not* rewritten into a `HOLD`. It is
    passed through so the environment classifies it as an invalid action and the
    constraint evaluator can count it. Silently substituting `HOLD` would make a
    broken agent look like a conservative one.
    """
    if not isinstance(decision, dict):
        return {
            "action": decision,
            "quantity": 0.0,
            "rationale": "",
            "malformed_decision": True,
        }
    return {
        "action": decision.get("action"),
        "quantity": decision.get("quantity", 0.0),
        "rationale": decision.get("rationale", ""),
        "malformed_decision": False,
    }


def run_episode(
    agent: BaseTradingAgent,
    environment: FinancialEnvironment,
    scenario_id: str,
    episode_id: Optional[str] = None,
    seed: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    logger: Optional[TraceLogger] = None,
    trace_phase: str = "static_evaluation",
) -> Trajectory:
    """Run one agent through one episode and return the recorded trajectory.

    The loop is: observe, decide, execute, record, repeat until the environment
    terminates. One action is submitted per market row, including the final row,
    matching the frozen environment contract.

    `seed` is recorded for provenance only. Every Phase 2 agent is deterministic
    and no component consumes it; it exists so that stochastic agents can be
    added later without changing the result schema.
    """
    if episode_id is None:
        episode_id = f"ep_{scenario_id}_{uuid4().hex[:8]}"

    trajectory = Trajectory(
        episode_id=episode_id,
        scenario_id=scenario_id,
        agent_id=agent.agent_id,
        agent_version=agent.version,
        seed=seed,
        environment_spec=environment.spec(),
        metadata=metadata,
    )

    observation = environment.reset()
    agent.reset()

    trajectory.initial_state = {
        "date": observation["date"],
        "market_price": observation["market_price"],
        "vix": observation["vix"],
        "cash": observation["portfolio"]["cash"],
        "holdings": observation["portfolio"]["holdings"],
        "total_value": observation["portfolio"]["total_value"],
    }

    if logger is not None:
        logger.start_episode(
            {
                "episode_id": episode_id,
                "phase": trace_phase,
                "scenario_id": scenario_id,
                "agent_id": agent.agent_id,
                "agent_version": agent.version,
                "seed": seed,
            }
        )

    # One action per market row; the guard catches a non-terminating environment
    # rather than hanging an evaluation run.
    max_steps = len(environment.market.df)
    step_index = 0
    done = False
    termination_reason = "unknown"

    while not done:
        if step_index >= max_steps:
            raise RuntimeError(
                f"Episode {episode_id} exceeded {max_steps} steps without terminating"
            )

        decision = _extract_decision(agent.act(observation))
        submitted_observation = observation
        date = observation["date"]

        next_observation, outcome, done, meta = environment.step(
            decision["action"], decision["quantity"]
        )
        termination_reason = meta.get("reason", "") if done else ""

        trajectory.add_step(
            step_index=step_index,
            date=date,
            observation=submitted_observation,
            action=decision,
            outcome=outcome,
        )

        if logger is not None:
            logger.log_step(
                step_index=step_index,
                date=date,
                observation=submitted_observation,
                decision=decision,
                outcome=outcome,
            )

        if next_observation is not None:
            observation = next_observation
        step_index += 1

    final_outcome = trajectory.steps[-1]["outcome"]
    trajectory.final_state = {
        "date": final_outcome["date"],
        "cash": final_outcome["cash"],
        "holdings": final_outcome["holdings"],
        "total_value": final_outcome["portfolio_value"],
        "cumulative_pnl": final_outcome["cumulative_pnl"],
        "steps_executed": len(trajectory.steps),
        "termination_reason": termination_reason,
    }

    if logger is not None:
        logger.save()

    return trajectory
