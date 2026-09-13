"""Target-agent contract for external evaluation (E0).

The evaluator must eventually drive heterogeneous agents (rule-based,
classical, ML, LLM, tool-using) without coupling to any single class
hierarchy. This module therefore defines a structural contract:

* :class:`AgentIdentity` — frozen agent id/version with validation.
* :class:`TargetAgent` — a :class:`typing.Protocol` (structural typing, no
  inheritance required) with ``identity``, ``reset()`` and ``act()``.
* :func:`validate_target_agent` / :func:`is_valid_target_agent` — explicit
  acceptance checks returning error lists (repository ``validate()``
  convention). Malformed agents are rejected, never coerced.
* :func:`invoke_act` — the single invocation path. It accepts **only**
  :class:`TargetObservation` and validates the returned order list shape.
  ``OraclePacket`` instances and plain mappings are rejected with
  ``TypeError``.

Reference shape: ``agents/financial_agent/base.py:BaseTradingAgent`` (which
uses the legacy single-asset ``{action, quantity}`` decision). E0 agents act
on the Indian multi-asset environment and therefore return an **order list**
(``environment/indian/actions.py:validate_orders`` shape). Adapting legacy
agents to this contract is E1 work, not E0.

Hidden chain-of-thought is never required: ``act`` returns orders only.
Optional observable metadata belongs on ``DecisionRecord.agent_metadata``,
not on the agent return value.

Deterministic replay: ``reset()`` must clear episode-local state; agents
should be deterministic given the same observation sequence, but
stochasticity is not rejected here (seeds/provenance are E1 concerns).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Protocol, Sequence

from evaluation.contracts.fingerprints import fingerprint_of_dict
from evaluation.contracts.oracle import OraclePacket, TargetObservation


@dataclass(frozen=True)
class AgentIdentity:
    """Stable id/version pair identifying one target agent build."""

    agent_id: str
    version: str

    def __post_init__(self) -> None:
        for field_name in ("agent_id", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> dict:
        return {"agent_id": self.agent_id, "version": self.version}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgentIdentity":
        if not isinstance(payload, Mapping):
            raise TypeError("AgentIdentity payload must be a mapping")
        try:
            agent_id = payload["agent_id"]
            version = payload["version"]
        except KeyError as exc:
            raise ValueError(
                f"AgentIdentity payload missing {exc}"
            ) from exc
        extra = set(payload) - {"agent_id", "version"}
        if extra:
            raise ValueError(f"unknown AgentIdentity fields: {sorted(extra)}")
        return cls(agent_id=agent_id, version=version)

    def fingerprint(self) -> str:
        """Deterministic identity over id + version."""
        return fingerprint_of_dict(self.to_dict())

    def __str__(self) -> str:
        return f"{self.agent_id}@{self.version}"


class TargetAgent(Protocol):
    """Structural contract for any evaluable trading agent.

    ``identity`` identifies the agent build. ``reset()`` clears
    episode-local state without discarding persistent adaptation memory.
    ``act()`` maps one validated :class:`TargetObservation` to a list of
    order mappings (possibly empty for HOLD). ``adapt()`` is optional and,
    when present, must be callable.
    """

    @property
    def identity(self) -> AgentIdentity:
        ...

    def reset(self) -> None:
        ...

    def act(
        self, observation: TargetObservation
    ) -> Sequence[Mapping[str, Any]]:
        ...

    def adapt(self, intervention: Mapping[str, Any]) -> None:
        ...


def validate_target_agent(candidate: Any) -> List[str]:
    """Check a candidate against the target-agent contract.

    Returns a list of error strings; empty means the agent is accepted.
    Never raises on malformed input and never calls ``act`` (validation
    must have no side effects on the agent).
    """
    errors: List[str] = []
    if candidate is None:
        return ["agent must not be None"]
    identity = getattr(candidate, "identity", None)
    if not isinstance(identity, AgentIdentity):
        errors.append("agent.identity must be an AgentIdentity")
    reset = getattr(candidate, "reset", None)
    if not callable(reset):
        errors.append("agent.reset must be callable")
    act = getattr(candidate, "act", None)
    if not callable(act):
        errors.append("agent.act must be callable")
    if hasattr(candidate, "adapt") and not callable(candidate.adapt):
        errors.append("agent.adapt, when present, must be callable")
    return errors


def is_valid_target_agent(candidate: Any) -> bool:
    """True when :func:`validate_target_agent` reports no errors."""
    return validate_target_agent(candidate) == []


def invoke_act(
    agent: Any, observation: Any
) -> Sequence[Mapping[str, Any]]:
    """Invoke ``agent.act`` on the single trusted invocation path.

    Args:
        agent: a candidate target agent (structurally validated first).
        observation: must be a :class:`TargetObservation`. ``OraclePacket``
            instances and plain mappings are rejected even when their
            content looks identical.

    Returns:
        The agent's order list (each entry a mapping; possibly empty).

    Raises:
        TypeError: on an untrusted observation, an invalid agent, or a
            malformed return value. No silent substitution is performed:
            a broken agent looks broken, never conservative.
    """
    if isinstance(observation, OraclePacket):
        raise TypeError(
            "an OraclePacket is evaluator-only and can never be passed "
            "to a target agent"
        )
    if not isinstance(observation, TargetObservation):
        raise TypeError(
            "target agents accept only TargetObservation; "
            f"got {type(observation).__name__}. Build it via "
            "TargetObservation.from_environment_state(...)."
        )
    errors = validate_target_agent(agent)
    if errors:
        raise TypeError(f"invalid target agent: {errors}")
    orders = agent.act(observation)
    if isinstance(orders, Mapping) or isinstance(orders, (str, bytes)):
        raise TypeError(
            "agent.act must return a sequence of order mappings, "
            f"got {type(orders).__name__}"
        )
    if not isinstance(orders, Sequence):
        raise TypeError(
            "agent.act must return a sequence of order mappings, "
            f"got {type(orders).__name__}"
        )
    checked = list(orders)
    for index, order in enumerate(checked):
        if not isinstance(order, Mapping):
            raise TypeError(
                f"agent.act order [{index}] must be a mapping, "
                f"got {type(order).__name__}"
            )
    return checked
