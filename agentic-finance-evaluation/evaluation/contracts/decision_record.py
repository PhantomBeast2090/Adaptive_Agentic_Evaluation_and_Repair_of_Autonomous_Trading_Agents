"""DecisionRecord: one normalized raw observable agent decision (E0).

A ``DecisionRecord`` is a **raw observable event**, not an evaluation. It
captures what the agent submitted, how the environment validated and
executed it, and the portfolio consequence — all copied from existing
environment outputs, never recomputed:

* observation identity: ``state_fingerprint`` (links the full
  ``EnvironmentState`` without duplicating it) plus visible/unavailable
  asset lists derived from ``AssetSlot`` statuses;
* action: ``submitted_orders`` (the
  ``environment/indian/actions.py:validate_orders`` input shape);
* validation: per-order reason-coded outcomes (``VALIDATED`` /
  ``NOOP_*``);
* execution: per-order fills copied from ``OrderResult.to_dict()``;
* consequence: ``portfolio_before``/``portfolio_after`` snapshots
  (``PortfolioView.to_dict()`` shape) and ``reward`` defined strictly as
  ``total_equity_after - total_equity_before`` (the environment's own
  reward definition: portfolio-value change inclusive of costs).

Derived claims (metrics, failures, diagnoses) belong on
``BehavioralEvidence``/``Hypothesis``, never here.

Records are frozen dataclasses. Sequence fields are coerced to tuples and
mapping fields are copied at construction; ``fingerprint()`` covers every
field. Optional agent-provided metadata (``confidence``, ``rationale``,
``tool_calls``, ``retrieved_information``) is whitelisted and validated;
hidden chain-of-thought is never required and has no field.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw

# Closed vocabulary for optional agent-provided observable metadata.
# Anything else (in particular hidden chain-of-thought) has no field.
AGENT_METADATA_FIELDS = (
    "confidence",
    "rationale",
    "tool_calls",
    "retrieved_information",
)


def _require_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("decision_timestamp must be a YYYY-MM-DD string")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"decision_timestamp must be YYYY-MM-DD, got {value!r}"
        ) from exc
    return value


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_finite_number(value: object, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value != value
        or value in (float("inf"), float("-inf"))
    ):
        raise ValueError(f"{field_name} must be a finite number")
    return float(value)


def _as_str_tuple(value: object, field_name: str) -> Tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} must be a tuple/list of strings")
    items = tuple(value)
    for item in items:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} entries must be non-empty strings")
    if len(set(items)) != len(items):
        raise ValueError(f"{field_name} must not contain duplicates")
    return items


def _as_mapping_tuple(value: object, field_name: str) -> Tuple[Dict[str, Any], ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} must be a tuple/list of mappings")
    out = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TypeError(
                f"{field_name}[{index}] must be a mapping"
            )
        out.append(dict(item))
    return tuple(out)


@dataclass(frozen=True)
class DecisionRecord:
    """One immutable raw observable decision."""

    decision_timestamp: str
    state_fingerprint: str
    visible_assets: Tuple[str, ...] = field(default_factory=tuple)
    unavailable_assets: Tuple[str, ...] = field(default_factory=tuple)
    submitted_orders: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    validation: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    executions: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    execution_price: Optional[float] = None
    transaction_cost: float = 0.0
    portfolio_before: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    portfolio_after: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    reward: float = 0.0
    environment_metadata: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]
    agent_metadata: Optional[Mapping[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision_timestamp",
            _require_timestamp(self.decision_timestamp),
        )
        object.__setattr__(
            self, "state_fingerprint",
            _require_non_empty_str(self.state_fingerprint, "state_fingerprint"),
        )
        visible = _as_str_tuple(self.visible_assets, "visible_assets")
        unavailable = _as_str_tuple(self.unavailable_assets, "unavailable_assets")
        overlap = set(visible) & set(unavailable)
        if overlap:
            raise ValueError(
                "visible_assets and unavailable_assets must be disjoint; "
                f"overlap: {sorted(overlap)}"
            )
        object.__setattr__(self, "visible_assets", visible)
        object.__setattr__(self, "unavailable_assets", unavailable)
        object.__setattr__(
            self, "submitted_orders",
            freeze(_as_mapping_tuple(self.submitted_orders, "submitted_orders")),
        )
        validation = _as_mapping_tuple(self.validation, "validation")
        for index, entry in enumerate(validation):
            if not isinstance(entry.get("status"), str) or not entry["status"]:
                raise ValueError(
                    f"validation[{index}] must carry a 'status' string"
                )
        object.__setattr__(self, "validation", freeze(validation))
        executions = _as_mapping_tuple(self.executions, "executions")
        for index, entry in enumerate(executions):
            for key in ("asset_id", "instrument", "execution_status"):
                if not isinstance(entry.get(key), str) or not entry[key]:
                    raise ValueError(
                        f"executions[{index}] must carry {key!r} as a string"
                    )
            _require_finite_number(
                entry.get("execution_price"),
                f"executions[{index}]['execution_price']",
            )
            _require_finite_number(
                entry.get("transaction_cost", 0.0),
                f"executions[{index}]['transaction_cost']",
            )
        object.__setattr__(self, "executions", freeze(executions))
        if self.execution_price is not None:
            price = _require_finite_number(self.execution_price, "execution_price")
            object.__setattr__(self, "execution_price", price)
            if len(executions) == 1 and price != executions[0]["execution_price"]:
                raise ValueError(
                    "execution_price must equal the single execution's "
                    "execution_price"
                )
        cost = _require_finite_number(self.transaction_cost, "transaction_cost")
        if cost < 0:
            raise ValueError("transaction_cost must be non-negative")
        object.__setattr__(self, "transaction_cost", cost)
        before = self._checked_portfolio(self.portfolio_before, "portfolio_before")
        after = self._checked_portfolio(self.portfolio_after, "portfolio_after")
        object.__setattr__(self, "portfolio_before", freeze(before))
        object.__setattr__(self, "portfolio_after", freeze(after))
        reward = _require_finite_number(self.reward, "reward")
        expected = after["total_equity"] - before["total_equity"]
        if reward != expected:
            raise ValueError(
                "reward must equal "
                "portfolio_after.total_equity - portfolio_before.total_equity "
                f"(got {reward}, expected {expected})"
            )
        object.__setattr__(self, "reward", reward)
        metadata = self._checked_env_metadata(self.environment_metadata)
        object.__setattr__(self, "environment_metadata", freeze(metadata))
        object.__setattr__(
            self, "agent_metadata",
            freeze(self._checked_agent_metadata(self.agent_metadata)),
        )

    @staticmethod
    def _checked_portfolio(value: object, field_name: str) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError(f"{field_name} must be a mapping")
        snapshot = dict(value)
        for amount_field in ("cash", "total_equity"):
            _require_finite_number(
                snapshot.get(amount_field),
                f"{field_name}[{amount_field!r}]",
            )
        return snapshot

    @staticmethod
    def _checked_env_metadata(value: object) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError("environment_metadata must be a mapping")
        metadata = dict(value)
        marker = metadata.get("market_fingerprint")
        if not isinstance(marker, str) or not marker:
            raise ValueError(
                "environment_metadata must carry a non-empty "
                "'market_fingerprint' tying the record to its environment"
            )
        return metadata

    @staticmethod
    def _checked_agent_metadata(
        value: Optional[Mapping[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise TypeError("agent_metadata must be a mapping or None")
        unknown = set(value) - set(AGENT_METADATA_FIELDS)
        if unknown:
            raise ValueError(
                "agent_metadata carries only observable metadata; "
                f"unknown fields: {sorted(unknown)}"
            )
        metadata = dict(value)
        if "confidence" in metadata:
            confidence = metadata["confidence"]
            if (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise ValueError("agent_metadata['confidence'] must be in [0, 1]")
            metadata["confidence"] = float(confidence)
        return metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_timestamp": self.decision_timestamp,
            "state_fingerprint": self.state_fingerprint,
            "visible_assets": list(self.visible_assets),
            "unavailable_assets": list(self.unavailable_assets),
            "submitted_orders": thaw(self.submitted_orders),
            "validation": thaw(self.validation),
            "executions": thaw(self.executions),
            "execution_price": self.execution_price,
            "transaction_cost": self.transaction_cost,
            "portfolio_before": thaw(self.portfolio_before),
            "portfolio_after": thaw(self.portfolio_after),
            "reward": self.reward,
            "environment_metadata": thaw(self.environment_metadata),
            "agent_metadata": (
                thaw(self.agent_metadata)
                if self.agent_metadata is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionRecord":
        if not isinstance(payload, Mapping):
            raise TypeError("DecisionRecord payload must be a mapping")
        known = {
            "decision_timestamp", "state_fingerprint", "visible_assets",
            "unavailable_assets", "submitted_orders", "validation",
            "executions", "execution_price", "transaction_cost",
            "portfolio_before", "portfolio_after", "reward",
            "environment_metadata", "agent_metadata",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown DecisionRecord fields: {sorted(extra)}")
        try:
            return cls(
                decision_timestamp=payload["decision_timestamp"],
                state_fingerprint=payload["state_fingerprint"],
                visible_assets=tuple(payload.get("visible_assets", ())),
                unavailable_assets=tuple(payload.get("unavailable_assets", ())),
                submitted_orders=tuple(payload.get("submitted_orders", ())),
                validation=tuple(payload.get("validation", ())),
                executions=tuple(payload.get("executions", ())),
                execution_price=payload.get("execution_price"),
                transaction_cost=payload.get("transaction_cost", 0.0),
                portfolio_before=payload["portfolio_before"],
                portfolio_after=payload["portfolio_after"],
                reward=payload.get("reward", 0.0),
                environment_metadata=payload["environment_metadata"],
                agent_metadata=payload.get("agent_metadata"),
            )
        except KeyError as exc:
            raise ValueError(
                f"DecisionRecord payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over every record field."""
        return fingerprint_of_dict(self.to_dict())
