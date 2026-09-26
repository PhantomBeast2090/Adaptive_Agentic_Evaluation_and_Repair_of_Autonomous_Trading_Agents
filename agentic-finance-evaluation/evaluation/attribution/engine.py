"""E5a deterministic decision-attribution engine.

Joins canonical ``DecisionRecord`` trajectories (produced by
``evaluation/baseline/runner.py:run_baseline``) with PIT-safe market legs
resolved through ``environment/indian/information_lookup.py``.

PIT contract (structural, evaluator-side only):
  * Pre-trend legs use exact-bar closes strictly BEFORE the decision
    timestamp (sessions t-1, t-2, ...). Same-bar and future closes never
    enter a pre-trend feature.
  * Forward / MAE / MFE / hold legs use the execution price and
    post-decision bars. They are labelled RETROSPECTIVE_EVALUATION_ONLY
    in row provenance and must never enter a TargetObservation.
  * The agent boundary is untouched: this engine never constructs or
    mutates a TargetObservation and never calls an agent.

Session arithmetic uses the experiment's own decision grid (an explicit
ordered list of YYYY-MM-DD session dates supplied by the caller), never
a synthetic wide grid. Missing bars yield None legs (never substituted,
never imputed); row-level attribution_status disambiguates
measured-missing from not-applicable.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Dict, List, Optional

from src.schemas.attribution import (
    AttributedDecision,
    AttributionOutcomes,
    DecisionAttributionResult,
    DecisionTimeState,
)
from environment.indian.clock import build_master_grid, load_default_resolver
from environment.indian.information_lookup import InformationLookup

PROVENANCE_LABEL = "RETROSPECTIVE_EVALUATION_ONLY"

# Participation vocabulary for attributed rows.
EXECUTED = "EXECUTED"
BLOCKED = "BLOCKED"
NO_ORDERS = "NO_ORDERS"

# Attribution decidability vocabulary.
DECIDABLE = "DECIDABLE"
UNDECIDABLE_MISSING_LEG = "UNDECIDABLE_MISSING_LEG"
NOT_APPLICABLE = "NOT_APPLICABLE"


def _equity_filter(instrument: str) -> Dict[str, str]:
    """Instrument -> InformationLookup id_filter for NSE equities."""
    symbol, _, series = instrument.partition(":")
    if not symbol or not series:
        raise ValueError(
            f"equity instrument must be 'SYMBOL:SERIES', got {instrument!r}"
        )
    return {"symbol": symbol, "series": series}


def instrument_filter(asset_id: str, instrument: str) -> Optional[Dict[str, str]]:
    """Resolve the exact-bar id_filter for one order leg.

    Mirrors environment/indian/environment.py::_execution_price so
    attribution legs reference the identical series the environment
    executed against. Single-series assets carry no filter.
    """
    if asset_id == "nse_equity":
        return _equity_filter(instrument)
    if asset_id == "mcx_gold":
        return {"contract_symbol": instrument}
    return None


def _execution_matches(
    execution: Dict[str, Any], asset_id: str, instrument: str
) -> bool:
    """True when an execution row belongs to one submitted order.

    Execution rows key instruments with the portfolio position key
    (``{asset_id}:{instrument}``, see environment/indian/portfolio.py:
    _instrument_key) while orders/validation carry the bare instrument.
    Both shapes are accepted; anything else never matches silently.
    """
    exec_instrument = execution.get("instrument", "")
    return exec_instrument in (instrument, f"{asset_id}:{instrument}")


def deterministic_decision_id(
    experiment_id: str,
    episode_id: str,
    decision_timestamp: str,
    asset_id: str,
    instrument: str,
    order_index: int,
) -> str:
    """Collision-free stable row identifier.

    Derivation: sha256 of the canonical tuple
    (experiment_id, episode_id, decision_timestamp, asset_id,
    instrument, order_index), truncated to 16 hex chars and prefixed
    with a human-readable stem. No randomness, no wall-clock.
    """
    stem = (
        f"{experiment_id}:{episode_id}:{decision_timestamp}:"
        f"{asset_id}:{instrument}:{order_index}"
    )
    digest = hashlib.sha256(stem.encode("utf-8")).hexdigest()[:16]
    safe = stem.replace(":", "-").replace("/", "_")
    return f"{safe}-{digest}"


class DecisionAttributionEngine:
    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.lookup = InformationLookup(base_dir=base_dir, strict=True)
        self.resolver = load_default_resolver(base_dir=base_dir)
        # Legacy fallback grid (broad NSE_CM coverage). Preferred path is
        # the caller-supplied experiment grid; see _resolve_grid.
        self.grid = build_master_grid(
            self.resolver, date(2010, 1, 1), date(2035, 12, 31)
        )
        self._grid_strings = [d.isoformat() for d in self.grid]

    # -- session arithmetic -------------------------------------------

    def _resolve_grid(
        self, experiment_grid: Optional[List[str]]
    ) -> List[str]:
        if experiment_grid is not None:
            if not experiment_grid:
                raise ValueError("experiment_grid must be non-empty")
            return list(experiment_grid)
        return list(self._grid_strings)

    def _shift_date(
        self,
        current: str,
        offset: int,
        experiment_grid: Optional[List[str]] = None,
    ) -> Optional[str]:
        try:
            grid = self._resolve_grid(experiment_grid)
            idx = grid.index(current)
            target = idx + offset
            if 0 <= target < len(grid):
                return grid[target]
            return None
        except ValueError:
            return None

    # -- market legs ---------------------------------------------------

    def _close(
        self, asset_id: str, instrument: str, session: Optional[str]
    ) -> Optional[float]:
        if session is None:
            return None
        try:
            price = self.lookup.bar_close(
                asset_id, instrument_filter(asset_id, instrument), session
            )
        except ValueError:
            return None
        if price is None or price <= 0:
            return None
        return float(price)

    def _ohlc(
        self, asset_id: str, instrument: str, session: Optional[str]
    ) -> Optional[Dict[str, float]]:
        """Exact-bar OHLC for MAE/MFE legs.

        Reads high/low/open directly from the canonical frame (the
        AssetSpec price_fields cover marks only). Exact-bar only: a
        missing bar or missing high/low yields None, never a substitute.
        """
        if session is None:
            return None
        try:
            import os

            import pandas as pd

            from environment.indian.registry import get_spec

            spec = get_spec(asset_id)
            filt = instrument_filter(asset_id, instrument) or {}
            # Evaluator-only OHLC read: _load_series restricts columns to
            # AssetSpec.price_fields (frozen contract), which exclude
            # high/low. Read the canonical CSV directly with the same
            # id_filter + exact-bar semantics; never a substitute bar.
            use = [spec.observation_col, "open", "high", "low", "close"]
            use += list(filt.keys())
            use = list(dict.fromkeys(use))
            path = os.path.join(self.base_dir, spec.csv_path)
            frame = pd.read_csv(path, usecols=lambda c: c in set(use))
            for col, val in filt.items():
                frame = frame[frame[col].astype(str) == str(val)]
            frame = frame.copy()
            frame["_obs"] = pd.to_datetime(
                frame[spec.observation_col], errors="coerce"
            )
            frame = frame.dropna(subset=["_obs"])
            hits = frame[frame["_obs"].dt.date.astype(str) == session]
            if hits.empty:
                return None
            row = hits.iloc[-1]
            out: Dict[str, float] = {}
            for col in ("open", "high", "low", "close"):
                if col in row:
                    try:
                        val = float(row[col])
                    except (TypeError, ValueError):
                        continue
                    if val == val and val > 0:
                        out[col] = val
            if "high" not in out or "low" not in out:
                return None
            return out
        except Exception:
            return None

    @staticmethod
    def _ret(new: Optional[float], old: Optional[float]) -> Optional[float]:
        if new is None or old is None or old <= 0:
            return None
        return (new - old) / old

    # -- main entry point ----------------------------------------------

    def attribute_trajectory(
        self,
        decision_records: List[Any],
        episode_id: str,
        arm: str,
        trajectory_fingerprint: str,
        run_id: str,
        experiment_id: str,
        experiment_grid: Optional[List[str]] = None,
        context_descriptor: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> DecisionAttributionResult:
        """Attribute one episode trajectory.

        One output row per submitted order (execution-joined), plus one
        NOOP row per session with no submitted orders so participation
        and non-participation are never conflated. Arm-agnostic: arm is
        carried as a label only.
        """
        grid = self._resolve_grid(experiment_grid)
        attributed: List[AttributedDecision] = []
        activity_count = 0

        for record_obj in decision_records:
            record = (
                record_obj.to_dict()
                if hasattr(record_obj, "to_dict")
                else record_obj
            )
            dec_time = record["decision_timestamp"]
            orders = record.get("submitted_orders", []) or []
            executions = record.get("executions", []) or []

            if not orders:
                activity_count += self._append_noop_row(
                    attributed,
                    record,
                    dec_time,
                    episode_id,
                    arm,
                    experiment_id,
                    grid,
                    context_descriptor,
                )
                continue

            for order_idx, order in enumerate(orders):
                asset_id = order.get("asset_id", "")
                instrument = order.get("instrument", asset_id)
                action = order.get("side", "NOOP")
                try:
                    quantity = float(
                        order.get(
                            "quantity", order.get("requested_quantity", 0.0)
                        )
                    )
                except (TypeError, ValueError):
                    quantity = 0.0

                matched = [
                    ex
                    for ex in executions
                    if ex.get("asset_id") == asset_id
                    and _execution_matches(ex, asset_id, instrument)
                ]
                # Fallback: legacy single-execution records keyed by asset.
                if not matched:
                    matched = [
                        ex for ex in executions if ex.get("asset_id") == asset_id
                    ]
                exec_price: Optional[float] = None
                exec_status: Optional[str] = None
                if matched and matched[0].get("execution_price") is not None:
                    try:
                        exec_price = float(matched[0]["execution_price"])
                    except (TypeError, ValueError):
                        exec_price = None
                    exec_status = matched[0].get("execution_status")

                validation = record.get("validation", []) or []
                block_reason = self._block_reason(
                    validation, asset_id, instrument
                )

                if exec_price is not None and exec_price > 0:
                    participation = EXECUTED
                elif block_reason is not None:
                    participation = f"{BLOCKED}_{block_reason}"
                else:
                    participation = BLOCKED

                row = self._build_order_row(
                    record=record,
                    dec_time=dec_time,
                    episode_id=episode_id,
                    arm=arm,
                    experiment_id=experiment_id,
                    order_index=order_idx,
                    asset_id=asset_id,
                    instrument=instrument,
                    action=action,
                    quantity=quantity,
                    exec_price=exec_price,
                    exec_status=exec_status,
                    participation=participation,
                    grid=grid,
                    context_descriptor=context_descriptor,
                )
                attributed.append(row)
                activity_count += 1

        result_kwargs: Dict[str, Any] = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "episode_id": episode_id,
            "arm": arm,
            "trajectory_fingerprint": trajectory_fingerprint,
            "attributed_decisions": attributed,
            "activity_count": activity_count,
            "context_descriptor": context_descriptor,
        }
        if grid:
            result_kwargs["grid_start"] = grid[0]
            result_kwargs["grid_end"] = grid[-1]
        if created_at is not None:
            result_kwargs["created_at"] = created_at
        return DecisionAttributionResult(**result_kwargs)

    # -- row builders ----------------------------------------------------

    def _pit_snapshot(
        self, asset_id: str, instrument: str, dec_time: str
    ) -> Dict[str, Any]:
        """Evaluator-side re-resolution of the PIT-visible slot.

        Uses get_information (observation-lag / vintage paths), never
        bar_close, so the snapshot carries the same observation_date /
        availability_date / vintage / status the agent saw.
        """
        try:
            slot = self.lookup.get_information(
                asset_id,
                dec_time,
                "explicit",
                instrument_filter(asset_id, instrument),
            )
            return {
                "asset_id": slot.asset_id,
                "status": slot.status,
                "observation_date": slot.observation_date,
                "availability_date": slot.availability_date,
                "vintage": slot.vintage,
                "values": dict(slot.values),
                "reason": slot.reason,
            }
        except Exception as exc:  # fail-closed: record the refusal
            return {"asset_id": asset_id, "status": "LOOKUP_REFUSED",
                    "reason": str(exc)}

    def _build_order_row(
        self,
        record: Dict[str, Any],
        dec_time: str,
        episode_id: str,
        arm: str,
        experiment_id: str,
        order_index: int,
        asset_id: str,
        instrument: str,
        action: str,
        quantity: float,
        exec_price: Optional[float],
        exec_status: Optional[str],
        participation: str,
        grid: List[str],
        context_descriptor: Optional[str],
    ) -> AttributedDecision:
        # PIT-pure pre-trend: closes strictly before the decision.
        c_tm1 = self._close(asset_id, instrument, self._shift_date(dec_time, -1, grid))
        c_tm2 = self._close(asset_id, instrument, self._shift_date(dec_time, -2, grid))
        c_tm4 = self._close(asset_id, instrument, self._shift_date(dec_time, -4, grid))
        c_tm6 = self._close(asset_id, instrument, self._shift_date(dec_time, -6, grid))
        pre_1d = self._ret(c_tm1, c_tm2)
        pre_3d = self._ret(c_tm1, c_tm4)
        pre_5d = self._ret(c_tm1, c_tm6)

        # Evaluator-only forward legs from the execution price.
        c_t0 = self._close(asset_id, instrument, dec_time)
        c_tp1 = self._close(asset_id, instrument, self._shift_date(dec_time, 1, grid))
        c_tp3 = self._close(asset_id, instrument, self._shift_date(dec_time, 3, grid))
        ref = exec_price if exec_price and exec_price > 0 else None
        fwd_1d = self._ret(c_tp1, ref)
        fwd_3d = self._ret(c_tp3, ref)
        hold_3d = self._ret(c_tp3, c_t0)

        mae, mfe = self._excursion(
            asset_id, instrument, dec_time, grid, ref, action
        )
        opportunity = self._opportunity(action, fwd_3d, participation)

        status = self._decide_status(
            participation, [pre_1d, fwd_1d, fwd_3d]
        )

        agent_meta = record.get("agent_metadata") or {}
        context_version = agent_meta.get("retrieved_information")
        if context_version is None:
            context_version = context_descriptor

        dt_state = DecisionTimeState(
            decision_timestamp=dec_time,
            instrument=instrument,
            action=action,
            quantity=quantity,
            execution_price=ref if ref is not None else 0.0,
            portfolio_before=record.get("portfolio_before", {}),
            portfolio_after=record.get("portfolio_after", {}),
            state_fingerprint=record.get("state_fingerprint", ""),
            market_features={
                "pit_snapshot": self._pit_snapshot(
                    asset_id, instrument, dec_time
                ),
                "market_fingerprint": (
                    record.get("environment_metadata", {}) or {}
                ).get("market_fingerprint"),
            },
            agent_context_version=(
                str(context_version)
                if context_version is not None
                else context_descriptor
            ),
        )
        outcomes = AttributionOutcomes(
            pre_trend_1d=pre_1d,
            pre_trend_3d=pre_3d,
            pre_trend_5d=pre_5d,
            forward_return_1d=fwd_1d,
            forward_return_3d=fwd_3d,
            mae=mae,
            mfe=mfe,
            hold_return=hold_3d,
            opportunity_return=opportunity,
        )
        return AttributedDecision(
            decision_id=deterministic_decision_id(
                experiment_id, episode_id, dec_time,
                asset_id, instrument, order_index,
            ),
            episode_id=episode_id,
            arm=arm,
            decision_time_state=dt_state,
            outcomes=outcomes,
            participation_status=participation,
            attribution_status=status,
            provenance={
                "classification": PROVENANCE_LABEL,
                "execution_status": exec_status,
                "reference_price": ref,
                "pre_trend_basis": "exact-bar closes strictly before decision",
                "forward_basis": "execution price to post-decision exact bars",
            },
        )

    def _append_noop_row(
        self,
        attributed: List[AttributedDecision],
        record: Dict[str, Any],
        dec_time: str,
        episode_id: str,
        arm: str,
        experiment_id: str,
        grid: List[str],
        context_descriptor: Optional[str],
    ) -> int:
        """One NOOP row per order-less session (never a fake opportunity)."""
        agent_meta = record.get("agent_metadata") or {}
        context_version = agent_meta.get("retrieved_information")
        if context_version is None:
            context_version = context_descriptor
        dt_state = DecisionTimeState(
            decision_timestamp=dec_time,
            instrument="NOOP",
            action="HOLD",
            quantity=0.0,
            execution_price=0.0,
            portfolio_before=record.get("portfolio_before", {}),
            portfolio_after=record.get("portfolio_after", {}),
            state_fingerprint=record.get("state_fingerprint", ""),
            market_features={
                "market_fingerprint": (
                    record.get("environment_metadata", {}) or {}
                ).get("market_fingerprint"),
            },
            agent_context_version=(
                str(context_version)
                if context_version is not None
                else context_descriptor
            ),
        )
        outcomes = AttributionOutcomes(
            opportunity_return=None,  # no counterfactual trade invented
        )
        attributed.append(
            AttributedDecision(
                decision_id=deterministic_decision_id(
                    experiment_id, episode_id, dec_time,
                    "noop", "NOOP", 0,
                ),
                episode_id=episode_id,
                arm=arm,
                decision_time_state=dt_state,
                outcomes=outcomes,
                participation_status=NO_ORDERS,
                attribution_status=NOT_APPLICABLE,
                provenance={
                    "classification": PROVENANCE_LABEL,
                    "note": "agent submitted no orders; no counterfactual "
                            "trade defined",
                },
            )
        )
        return 1

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _block_reason(
        validation: List[Dict[str, Any]], asset_id: str, instrument: str
    ) -> Optional[str]:
        for entry in validation:
            if entry.get("asset_id") != asset_id:
                continue
            if instrument and entry.get("instrument") not in (instrument, None, ""):
                if entry.get("instrument") != instrument:
                    continue
            status = str(entry.get("status", ""))
            if status and status != "VALIDATED":
                return status
        return None

    def _excursion(
        self,
        asset_id: str,
        instrument: str,
        dec_time: str,
        grid: List[str],
        ref: Optional[float],
        action: str,
    ) -> Any:
        """Daily-bar MAE/MFE over t+1..t+3 vs the execution price.

        BUY:  MAE=(min low-ref)/ref, MFE=(max high-ref)/ref.
        SELL: signs flipped (favourable = price fall).
        NOOP/blocked (ref None) or missing high/low legs -> (None, None)
        with attribution_status carrying the reason. No intraday
        manufacture: daily high/low only, documented in provenance.
        """
        if ref is None or ref <= 0:
            return None, None
        legs = []
        for offset in (1, 2, 3):
            bar = self._ohlc(
                asset_id, instrument, self._shift_date(dec_time, offset, grid)
            )
            if bar is not None:
                legs.append(bar)
        if not legs:
            return None, None
        lo = min(b["low"] for b in legs)
        hi = max(b["high"] for b in legs)
        if action == "SELL":
            return (ref - hi) / ref, (ref - lo) / ref
        return (lo - ref) / ref, (hi - ref) / ref

    @staticmethod
    def _opportunity(
        action: str, fwd_3d: Optional[float], participation: str
    ) -> Optional[float]:
        if not participation.startswith(EXECUTED) or fwd_3d is None:
            return None
        if action == "SELL":
            return -fwd_3d
        if action == "BUY":
            return fwd_3d
        return None

    @staticmethod
    def _decide_status(
        participation: str, legs: List[Optional[float]]
    ) -> str:
        if participation == NO_ORDERS:
            return NOT_APPLICABLE
        if all(leg is None for leg in legs):
            return UNDECIDABLE_MISSING_LEG
        return DECIDABLE
