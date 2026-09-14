"""Trusted observation bridge for baseline evaluation (E1).

E0's ``TargetObservation.from_environment_state`` intentionally requires an
actual ``EnvironmentState`` instance and rejects serialized dictionaries.
The public ``IndianMultiAssetEnvironment.reset/step`` APIs expose only
dictionaries, while the environment builds ``EnvironmentState`` instances
internally in ``_state_at``.

This module is the single, contained adapter around that internal path:

* :func:`observe_current` calls the environment's own state constructor at
  its current grid position and wraps the result through the E0 trusted
  path. No state is reimplemented, no dictionary is reconstructed into a
  trusted object, and the frozen environment is not modified.
* Underscore access to ``_state_at`` appears **only** in this module. Every
  expectation about the environment's API (class, ``grid``/``index``/
  ``done`` attributes, ``_state_at`` returning ``EnvironmentState``) is
  checked explicitly so an upstream change fails loudly here instead of
  leaking silently downstream.

E1 tests pin this surface; if the environment ever exposes a public
``EnvironmentState`` accessor, this adapter should delegate to it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from environment.indian.environment import IndianMultiAssetEnvironment
from environment.indian.information_lookup import STATUS_AVAILABLE
from environment.indian.state import EnvironmentState
from evaluation.contracts.oracle import TargetObservation

# Method name depended upon, referenced symbolically so the dependency is
# greppable and any rename breaks loudly at call time, not silently.
_TRUSTED_STATE_METHOD = "_state_at"


def observe_current(env: IndianMultiAssetEnvironment) -> TargetObservation:
    """Observe the environment's current decision point through E0 trust.

    Args:
        env: a live ``IndianMultiAssetEnvironment`` positioned at the
            decision session to observe (i.e. ``env.done`` is False and
            ``env.index`` addresses the session the agent must act on).

    Returns:
        The validated ``TargetObservation`` for that session.

    Raises:
        TypeError: if ``env`` is not an ``IndianMultiAssetEnvironment`` or
            its state constructor stops returning ``EnvironmentState``.
        ValueError: if the episode is done or the grid position is invalid.
        AttributeError: if the expected internal state path is absent
            (fail loudly on environment API drift).
    """
    if not isinstance(env, IndianMultiAssetEnvironment):
        raise TypeError(
            "baseline observations come only from "
            "IndianMultiAssetEnvironment; "
            f"got {type(env).__name__}"
        )
    if env.done:
        raise ValueError(
            "episode is done; there is no current decision to observe"
        )
    grid = env.grid
    index = env.index
    if not isinstance(index, int) or not 0 <= index < len(grid):
        raise ValueError(
            f"environment grid position out of range: index={index!r}, "
            f"sessions={len(grid)}"
        )
    constructor = getattr(env, _TRUSTED_STATE_METHOD, None)
    if not callable(constructor):
        raise AttributeError(
            f"environment no longer exposes {_TRUSTED_STATE_METHOD}(); "
            "the trusted observation path must be re-established explicitly"
        )
    state = constructor(grid[index])
    if not isinstance(state, EnvironmentState):
        raise TypeError(
            "environment state path must return EnvironmentState; "
            f"got {type(state).__name__}"
        )
    return TargetObservation.from_environment_state(state)


def split_visibility(
    observation: TargetObservation,
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Split observed asset keys into visible vs unavailable (sorted).

    A slot counts as visible only when its status is ``AVAILABLE``; every
    other status (``OBS_MISSING``, ``INFO_UNAVAILABLE``, ``CAL_UNKNOWN``,
    ``CAL_CLOSED``, ``CONSTRAINT_FAIL``) counts as unavailable. The split
    is derived from the trusted payload the agent actually saw.
    """
    if not isinstance(observation, TargetObservation):
        raise TypeError(
            "visibility must be derived from a TargetObservation, "
            f"got {type(observation).__name__}"
        )
    payload = observation.to_dict()
    visible: List[str] = []
    unavailable: List[str] = []
    for block_name in ("market", "macro"):
        block = payload[block_name]
        for key in block:
            if block[key].get("status") == STATUS_AVAILABLE:
                visible.append(key)
            else:
                unavailable.append(key)
    return tuple(sorted(visible)), tuple(sorted(unavailable))


def observation_portfolio(observation: TargetObservation) -> Dict[str, Any]:
    """Return a deep copy of the trusted portfolio snapshot for records."""
    if not isinstance(observation, TargetObservation):
        raise TypeError(
            "portfolio snapshots must come from a TargetObservation, "
            f"got {type(observation).__name__}"
        )
    portfolio = observation.to_dict()["portfolio"]
    if not isinstance(portfolio, dict):
        raise TypeError("trusted portfolio block must be a mapping")
    return portfolio
