"""Intervention materialisation for diagnostic execution (E2-B).

E0 ``DiagnosticTest.intervention`` is an open mapping with a required
``type`` field, and its full content is part of the test fingerprint. E2-B
must honour that contract: it reuses the E0 representation (no competing
schema) and defines a small, closed, explicit mapping from intervention
type to environment configuration.

Supported types (each with a closed parameter set; unknown parameters are
rejected, never ignored):

* ``null_intervention`` — control arm: run the episode under baseline
  market conditions (baseline costs, baseline vintage policy, baseline
  strict PIT). Lets a diagnostic episode reproduce baseline mechanics.
* ``transaction_cost_shift`` — ``{multiplier}``: scale baseline
  transaction costs by a positive finite multiplier.
* ``transaction_cost_set`` — ``{costs_bps}``: set absolute costs in basis
  points (finite, non-negative).
* ``vintage_policy_shift`` — ``{vintage_policy}``: override the
  point-in-time vintage resolution policy. Strict PIT gating itself is
  never relaxed by any intervention.
* ``universe_restriction`` — ``{nse_equity?, mcx_gold?}``: narrow the
  episode universe to a non-empty subset of the baseline universe.

Anything else — unknown type, malformed parameter, out-of-baseline window
or universe, relaxed PIT — raises :class:`InvalidIntervention` with an
explicit reason. The executor converts that into a recorded ``INVALID``
result; an intervention is never silently turned into a no-op.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

SUPPORTED_INTERVENTION_TYPES = (
    "null_intervention",
    "transaction_cost_shift",
    "transaction_cost_set",
    "vintage_policy_shift",
    "universe_restriction",
)

VINTAGE_POLICIES = ("explicit", "earliest_available", "latest_available")

UNIVERSE_ASSETS = ("nse_equity", "mcx_gold")


class InvalidIntervention(Exception):
    """An intervention cannot be materialised; carries the explicit reason.

    Internal signal only: the executor converts it into a recorded
    ``INVALID`` DiagnosticTestResult. Never raised for caller type errors
    (those remain TypeError/ValueError at the executor boundary).
    """

    def __init__(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("InvalidIntervention requires a reason")
        super().__init__(reason)
        self.reason = reason


def _require_finite_number(value: object, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value != value
        or value in (float("inf"), float("-inf"))
    ):
        raise InvalidIntervention(f"{field_name} must be a finite number")
    return float(value)


def _checked_universe(
    value: object, field_name: str, baseline: Mapping[str, List[str]]
) -> Dict[str, List[str]]:
    if not isinstance(value, Mapping):
        raise InvalidIntervention(f"{field_name} must be a mapping")
    unknown = set(value) - set(UNIVERSE_ASSETS)
    if unknown:
        raise InvalidIntervention(
            f"{field_name} has unknown assets: {sorted(unknown)}"
        )
    checked: Dict[str, List[str]] = {}
    total = 0
    for asset_id in UNIVERSE_ASSETS:
        instruments = value.get(asset_id, ())
        if isinstance(instruments, str) or not isinstance(
            instruments, (tuple, list)
        ):
            raise InvalidIntervention(
                f"{field_name}[{asset_id!r}] must be a list of instruments"
            )
        items = [str(item) for item in instruments]
        for item in items:
            if not item:
                raise InvalidIntervention(
                    f"{field_name}[{asset_id!r}] holds an empty instrument"
                )
        allowed = set(baseline.get(asset_id, ()))
        outside = [item for item in items if item not in allowed]
        if outside:
            raise InvalidIntervention(
                f"{field_name}[{asset_id!r}] exceeds the baseline universe: "
                f"{sorted(outside)}"
            )
        checked[asset_id] = items
        total += len(items)
    if total == 0:
        raise InvalidIntervention(f"{field_name} must be non-empty")
    return checked


def resolve_env_config(
    *,
    intervention: Mapping[str, Any],
    baseline_spec: Mapping[str, Any],
    window: Tuple[str, str],
    episode_universe: Mapping[str, Any],
) -> Dict[str, Any]:
    """Materialise an intervention into an environment configuration.

    Args:
        intervention: the registered test's ``intervention`` mapping.
        baseline_spec: the baseline environment ``spec()`` (carries costs,
            vintage policy, strict PIT, cash, universes, grid bounds).
        window: requested ``(start_date, end_date)`` for the episode.
        episode_universe: requested tradable scope for the episode.

    Returns:
        A configuration dict for ``IndianMultiAssetEnvironment``.

    Raises:
        InvalidIntervention: unsupported type, malformed parameter, window
            outside the baseline grid, universe outside baseline, or any
            attempt to relax strict point-in-time gating.
    """
    if not isinstance(intervention, Mapping) or not intervention:
        raise InvalidIntervention("intervention must be a non-empty mapping")
    kind = intervention.get("type")
    if kind not in SUPPORTED_INTERVENTION_TYPES:
        raise InvalidIntervention(
            f"unsupported intervention type {kind!r}; "
            f"supported: {list(SUPPORTED_INTERVENTION_TYPES)}"
        )
    try:
        baseline_costs = float(baseline_spec["transaction_cost_bps"])
        baseline_vintage = str(baseline_spec["vintage_policy"])
        baseline_strict = bool(baseline_spec["strict_pit"])
        baseline_cash = float(baseline_spec["initial_cash"])
        grid_start = str(baseline_spec["grid_start"])
        grid_end = str(baseline_spec["grid_end"])
        baseline_universe = {
            "nse_equity": list(baseline_spec["equity_universe"]),
            "mcx_gold": list(baseline_spec["gold_universe"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidIntervention(
            f"baseline environment spec lacks required fields: {exc}"
        ) from exc

    start_date, end_date = window
    if not (grid_start <= start_date <= end_date <= grid_end):
        raise InvalidIntervention(
            "episode window must lie within the baseline grid "
            f"[{grid_start}, {grid_end}]; got [{start_date}, {end_date}]"
        )
    scope = _checked_universe(episode_universe, "episode universe", baseline_universe)

    costs_bps = baseline_costs
    vintage_policy = baseline_vintage
    params = dict(intervention)
    params.pop("type")

    if kind == "null_intervention":
        if params:
            raise InvalidIntervention(
                "null_intervention takes no parameters; "
                f"got {sorted(params)}"
            )
    elif kind == "transaction_cost_shift":
        if set(params) != {"multiplier"}:
            raise InvalidIntervention(
                "transaction_cost_shift requires exactly {multiplier}; "
                f"got {sorted(params)}"
            )
        multiplier = _require_finite_number(params["multiplier"], "multiplier")
        if multiplier <= 0:
            raise InvalidIntervention("multiplier must be positive")
        costs_bps = baseline_costs * multiplier
    elif kind == "transaction_cost_set":
        if set(params) != {"costs_bps"}:
            raise InvalidIntervention(
                "transaction_cost_set requires exactly {costs_bps}; "
                f"got {sorted(params)}"
            )
        costs_bps = _require_finite_number(params["costs_bps"], "costs_bps")
        if costs_bps < 0:
            raise InvalidIntervention("costs_bps must be non-negative")
    elif kind == "vintage_policy_shift":
        if set(params) != {"vintage_policy"}:
            raise InvalidIntervention(
                "vintage_policy_shift requires exactly {vintage_policy}; "
                f"got {sorted(params)}"
            )
        if params["vintage_policy"] not in VINTAGE_POLICIES:
            raise InvalidIntervention(
                f"unknown vintage_policy {params['vintage_policy']!r}; "
                f"known: {list(VINTAGE_POLICIES)}"
            )
        vintage_policy = str(params["vintage_policy"])
    elif kind == "universe_restriction":
        unknown = set(params) - set(UNIVERSE_ASSETS)
        if unknown:
            raise InvalidIntervention(
                f"universe_restriction has unknown parameters: "
                f"{sorted(unknown)}"
            )
        if not params:
            raise InvalidIntervention(
                "universe_restriction must name at least one asset list"
            )
        narrowed = _checked_universe(params, "restriction", baseline_universe)
        # Assets named in the restriction are narrowed to the intersection
        # with the episode scope; unnamed assets keep the episode scope.
        restricted = {}
        for asset_id in UNIVERSE_ASSETS:
            if asset_id in params:
                allowed = set(narrowed[asset_id])
                restricted[asset_id] = [
                    item for item in scope[asset_id] if item in allowed
                ]
            else:
                restricted[asset_id] = scope[asset_id]
        scope = restricted
        if sum(len(v) for v in scope.values()) == 0:
            raise InvalidIntervention(
                "universe_restriction leaves an empty episode universe"
            )

    return {
        "strict_pit": baseline_strict,
        "vintage_policy": vintage_policy,
        "transaction_cost_bps": costs_bps,
        "initial_cash": baseline_cash,
        "start_date": start_date,
        "end_date": end_date,
        "universe": scope,
    }
