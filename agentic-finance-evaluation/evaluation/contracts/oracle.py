"""Information-leakage boundary: target observations vs evaluator oracle.

Conceptual flow::

    Existing Indian Environment
            |
            v
    TargetObservation  (validated, PIT-gated; the ONLY input a target
            |            agent may receive)
            v
       Target Agent

    Oracle / future information
            |
            v
    OraclePacket  (evaluator-only; NEVER convertible to TargetObservation)

Trust model for E0:

* Provenance is by construction path: the only way to obtain a
  ``TargetObservation`` is :meth:`TargetObservation.from_environment_state`
  applied to an actual ``EnvironmentState`` produced by the existing Indian
  environment. The direct constructor and serialized dictionaries are
  rejected, so arbitrary mappings cannot be silently trusted.
* The accepted schema is closed: exactly the five
  ``EnvironmentState.to_dict()`` top-level keys. Any oracle-only field
  (future prices, later revisions, unseen states) changes the key set or
  the slot shapes and is rejected structurally.
* There is deliberately no ``OraclePacket.to_target_observation`` method
  and no shared base class; the only bridge the codebase offers in the
  oracle direction is a type error.
* This is structural, not cryptographic, provenance: a deliberately forged
  mapping with exactly the right shape cannot be distinguished. Forgery is
  outside the E0 threat model; accidental leakage is made impossible.

Do NOT modify ``InformationSet`` or temporal eligibility here. The
environment's PIT semantics remain the sole source of target observations;
this module only wraps and gates them.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from evaluation.contracts.fingerprints import fingerprint_of_dict, freeze, thaw

# Closed schema: exactly EnvironmentState.to_dict() top-level keys.
_TARGET_OBSERVATION_KEYS = (
    "decision_timestamp",
    "market",
    "macro",
    "portfolio",
    "calendar",
)

# Module-private construction token. Only from_environment_state holds it,
# so direct construction (TargetObservation({...})) always fails closed.
_TARGET_OBSERVATION_TOKEN: Any = object()


def _check_timestamp(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a YYYY-MM-DD string")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be YYYY-MM-DD, got {value!r}"
        ) from exc
    return value


def _check_slot_block(block: object, field_name: str) -> None:
    if not isinstance(block, Mapping):
        raise TypeError(f"{field_name} must be a mapping of asset slots")
    for key, slot in block.items():
        if not isinstance(slot, Mapping):
            raise TypeError(f"{field_name}[{key!r}] must be a slot mapping")
        expected = {
            "status", "venue", "observation_date", "availability_date",
            "vintage", "values", "reason",
        }
        if set(slot) != expected:
            raise ValueError(
                f"{field_name}[{key!r}] must match the environment slot schema"
            )
        if "status" not in slot or "values" not in slot:
            raise ValueError(
                f"{field_name}[{key!r}] must contain 'status' and 'values'"
            )
        if not isinstance(slot["status"], str) or not slot["status"]:
            raise ValueError(f"{field_name}[{key!r}] has an invalid status")
        if not isinstance(slot["values"], Mapping):
            raise TypeError(f"{field_name}[{key!r}]['values'] must be a mapping")


def _validate_target_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("environment state must be a mapping")
    keys = set(payload.keys())
    expected = set(_TARGET_OBSERVATION_KEYS)
    if keys != expected:
        raise ValueError(
            "target observation must carry exactly the environment keys "
            f"{sorted(expected)}; got {sorted(keys)}. Extra keys "
            "(including any oracle-only fields) are rejected."
        )
    _check_timestamp(payload["decision_timestamp"], "decision_timestamp")
    _check_slot_block(payload["market"], "market")
    _check_slot_block(payload["macro"], "macro")
    portfolio = payload["portfolio"]
    if not isinstance(portfolio, Mapping):
        raise TypeError("portfolio block must be a mapping")
    for amount_field in ("cash", "total_equity"):
        amount = portfolio.get(amount_field)
        if (
            not isinstance(amount, (int, float))
            or isinstance(amount, bool)
            or amount != amount
        ):
            raise ValueError(
                f"portfolio[{amount_field!r}] must be a finite number"
            )
    calendar = payload["calendar"]
    if not isinstance(calendar, Mapping):
        raise TypeError("calendar block must be a mapping")
    for venue, status in calendar.items():
        if not isinstance(status, str) or not status:
            raise ValueError(
                f"calendar[{venue!r}] must be a non-empty string"
            )
    return payload


class TargetObservation:
    """A validated point-in-time observation for one target-agent decision.

    Instances are immutable snapshots: the payload is deep-copied on entry
    and every accessor returns a deep copy, so neither the agent nor the
    caller can mutate the stored observation.
    """

    __slots__ = ("_payload",)

    def __init__(self, payload: Mapping[str, Any], *, _token: Any = None) -> None:
        if _token is not _TARGET_OBSERVATION_TOKEN:
            raise TypeError(
                "TargetObservation has no public constructor: build it via "
                "TargetObservation.from_environment_state(...). Arbitrary "
                "mappings are never silently trusted as target observations."
            )
        # Defence in depth: even the trusted path re-validates.
        self._payload: Dict[str, Any] = copy.deepcopy(
            dict(_validate_target_payload(payload))
        )

    @classmethod
    def from_environment_state(cls, state: Any) -> "TargetObservation":
        """Wrap validated environment output as a trusted observation.

        Args:
            state: actual ``EnvironmentState`` returned by the existing
                Indian environment's internal state construction path.
                Passing an existing ``TargetObservation`` returns it
                unchanged.

        Raises:
            TypeError: if ``state`` is an ``OraclePacket``, a serialized
                dictionary, or any other non-``EnvironmentState`` input.
        """
        if isinstance(state, OraclePacket):
            raise TypeError(
                "an OraclePacket is evaluator-only and can never become a "
                "TargetObservation"
            )
        if isinstance(state, TargetObservation):
            return state
        from environment.indian.state import EnvironmentState

        if not isinstance(state, EnvironmentState):
            raise TypeError(
                "target observations must be built from an "
                "EnvironmentState instance; "
                f"got {type(state).__name__}"
            )
        return cls(state.to_dict(), _token=_TARGET_OBSERVATION_TOKEN)

    @property
    def decision_timestamp(self) -> str:
        return self._payload["decision_timestamp"]

    def __getitem__(self, key: str) -> Any:
        return copy.deepcopy(self._payload[key])

    def __contains__(self, key: object) -> bool:
        return key in self._payload

    def keys(self) -> tuple:
        return tuple(self._payload.keys())

    def to_dict(self) -> Dict[str, Any]:
        """Return a deep copy of the trusted payload."""
        return copy.deepcopy(self._payload)

    def fingerprint(self) -> str:
        """Deterministic identity over the full trusted payload."""
        return fingerprint_of_dict(self._payload)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, TargetObservation)
            and self._payload == other._payload
        )

    def __hash__(self) -> int:
        raise TypeError("TargetObservation is unhashable; use fingerprint()")

    def __repr__(self) -> str:
        return (
            "TargetObservation("
            f"decision_timestamp={self.decision_timestamp!r})"
        )


@dataclass(frozen=True)
class OraclePacket:
    """Evaluator-only information that must never reach the target agent.

    Carries oracle/future content (later prices, later revisions, future
    market states) for diagnosis. The ``evaluator_only`` flag must be True;
    there is deliberately no conversion method to ``TargetObservation``.

    E0 defines the container only. No oracle *collection* logic lives here.
    """

    packet_id: str
    source: str
    as_of: str
    content: Mapping[str, Any] = field(default_factory=dict)
    evaluator_only: bool = True
    label: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.packet_id, str) or not self.packet_id.strip():
            raise ValueError("packet_id must be a non-empty string")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        _check_timestamp(self.as_of, "as_of")
        if not isinstance(self.content, Mapping):
            raise TypeError("content must be a mapping")
        object.__setattr__(self, "content", freeze(self.content))
        if self.evaluator_only is not True:
            raise ValueError("OraclePacket.evaluator_only must be True")
        if self.label is not None and not isinstance(self.label, str):
            raise TypeError("label must be a string or None")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "source": self.source,
            "as_of": self.as_of,
            "content": thaw(self.content),
            "evaluator_only": True,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OraclePacket":
        if not isinstance(payload, Mapping):
            raise TypeError("OraclePacket payload must be a mapping")
        known = {"packet_id", "source", "as_of", "content",
                 "evaluator_only", "label"}
        extra = set(payload) - known
        if extra:
            raise ValueError(f"unknown OraclePacket fields: {sorted(extra)}")
        try:
            return cls(
                packet_id=payload["packet_id"],
                source=payload["source"],
                as_of=payload["as_of"],
                content=payload.get("content", {}),
                evaluator_only=payload.get("evaluator_only", True),
                label=payload.get("label"),
            )
        except KeyError as exc:
            raise ValueError(
                f"OraclePacket payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        """Deterministic identity over all packet fields."""
        return fingerprint_of_dict(self.to_dict())
