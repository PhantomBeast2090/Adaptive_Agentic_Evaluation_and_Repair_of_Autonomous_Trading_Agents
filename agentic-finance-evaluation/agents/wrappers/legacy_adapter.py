"""Legacy single-asset adapter (M-R1, additive).

Adapts legacy ``BaseTradingAgent`` dict-decision agents
(``{action, quantity, rationale}``) to the E0 order-list contract so the
deterministic synthetic agents (LossChasing, VolatilityBlind, Flawless
control) can run inside ``run_baseline`` for the controlled repair
benchmarks (M-R2/R3). The adapter translates observations and orders only;
it never alters the wrapped agent's logic or state ownership rules.

Legacy observation synthesis (documented approximation, pinned by tests):
  vix           <- frozen ``indiavix`` slot close (default 20.0 if unusable)
  market_price  <- first AVAILABLE ``nse_equity:*`` slot close, else 1.0
  portfolio     <- {cash, holdings: 0.0, total_value: total_equity}

Order translation:
  BUY qty>0   -> [build_order(asset_id, instrument, BUY, qty)]
  SELL qty>0  -> [build_order(..., SELL, min(qty, held_qty))]
  HOLD/zero/invalid -> []
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Sequence

from benchmarks.observation import (
    as_dict,
    build_order,
    read_cash,
    read_indicator_close,
    read_positions,
)
from evaluation.contracts.agent import AgentIdentity, validate_target_agent

VIX_SLOT = "indiavix"
DEFAULT_VIX = 20.0
DEFAULT_PRICE = 1.0


class LegacyAgentAdapter:
    """E0 order-list shell around a legacy dict-decision agent."""

    def __init__(
        self, base_agent: Any, asset_id: str, instrument: str
    ) -> None:
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError("asset_id must be a non-empty string")
        if not isinstance(instrument, str) or not instrument:
            raise ValueError("instrument must be a non-empty string")
        identity = getattr(base_agent, "identity", None)
        if identity is not None and not isinstance(identity, AgentIdentity):
            raise TypeError("base identity must be an AgentIdentity")
        if not callable(getattr(base_agent, "act", None)):
            raise TypeError("base agent must have a callable act")
        if not callable(getattr(base_agent, "reset", None)):
            raise TypeError("base agent must have a callable reset")
        self._base = copy.deepcopy(base_agent)
        self._asset_id = asset_id
        self._instrument = instrument
        if identity is None:
            agent_id = getattr(base_agent, "agent_id", "legacy-agent")
            version = getattr(base_agent, "version", "v0")
            identity = AgentIdentity(str(agent_id), str(version))
        self._identity = identity

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def base(self) -> Any:
        """The owned legacy copy (rollback/inspection handle)."""
        return self._base

    def policy_snapshot(self) -> Mapping[str, Any]:
        """Fingerprintable snapshot of the INNERMOST policy.

        The generic snapshot cannot traverse the adapter's owned nested
        copy, so the adapter exposes the inner snapshot directly. This
        keeps policy-preservation proofs working through wrapper stacks
        without modifying frozen snapshot code.
        """
        from evaluation.diagnostics.repair.application import (
            snapshot_policy,
        )

        return snapshot_policy(self._base)

    def reset(self) -> None:
        self._base.reset()

    def _legacy_observation(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        vix = read_indicator_close(payload, VIX_SLOT)
        cash = read_cash(payload)
        positions = read_positions(payload)
        price: float | None = None
        market = payload.get("market", {})
        if isinstance(market, Mapping):
            for key in sorted(market):
                if not key.startswith("nse_equity:"):
                    continue
                candidate = read_indicator_close(payload, key)
                if candidate is not None:
                    price = candidate
                    break
        held = positions.get(
            f"{self._asset_id}:{self._instrument}", 0.0
        )
        total_equity = payload.get("portfolio", {}).get("total_equity")
        return {
            "vix": vix if vix is not None else DEFAULT_VIX,
            "market_price": price if price is not None else DEFAULT_PRICE,
            "portfolio": {
                "cash": cash if cash is not None else 0.0,
                "holdings": held,
                "total_value": total_equity
                if isinstance(total_equity, (int, float))
                else 0.0,
            },
        }

    def act(self, observation: Any) -> Sequence[Mapping[str, Any]]:
        payload = as_dict(observation)
        decision = self._base.act(self._legacy_observation(payload))
        if not isinstance(decision, Mapping):
            return []
        action = decision.get("action")
        quantity = decision.get("quantity", 0.0)
        if (
            action not in ("BUY", "SELL")
            or isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or quantity <= 0
        ):
            return []
        if action == "SELL":
            positions = read_positions(payload)
            held = positions.get(
                f"{self._asset_id}:{self._instrument}", 0.0
            )
            quantity = min(float(quantity), held)
            if quantity <= 0:
                return []
        return [
            build_order(
                self._asset_id, self._instrument, action, float(quantity)
            )
        ]


def is_valid_legacy_adapter(candidate: Any) -> bool:
    """Structural check mirroring validate_target_agent for adapters."""
    from evaluation.contracts.agent import validate_target_agent

    return validate_target_agent(candidate) == []
