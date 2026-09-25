from typing import Any, Dict, List, Optional
from datetime import date
import pandas as pd
import copy

from src.schemas.attribution import (
    AttributedDecision, DecisionTimeState, AttributionOutcomes, DecisionAttributionResult
)
from environment.indian.information_lookup import InformationLookup
from environment.indian.clock import load_default_resolver, build_master_grid


class DecisionAttributionEngine:
    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.lookup = InformationLookup(base_dir=base_dir, strict=True)
        self.resolver = load_default_resolver(base_dir=base_dir)
        self.grid = build_master_grid(self.resolver, date(2010, 1, 1), date(2035, 12, 31))

    def _shift_date(self, current: str, offset: int) -> Optional[str]:
        try:
            d = date.fromisoformat(current)
            idx = self.grid.index(d)
            target = idx + offset
            if 0 <= target < len(self.grid):
                return self.grid[target].isoformat()
            return None
        except ValueError:
            return None

    def attribute_trajectory(
        self,
        decision_records: List[Any],
        episode_id: str,
        arm: str,
        trajectory_fingerprint: str,
        run_id: str,
        experiment_id: str,
    ) -> DecisionAttributionResult:
        attributed = []
        activity_count = 0
        
        for record_obj in decision_records:
            record = record_obj.to_dict() if hasattr(record_obj, "to_dict") else record_obj
            dec_time = record["decision_timestamp"]
            
            # Identify active orders/decisions
            orders = record.get("submitted_orders", [])
            for order in orders:
                asset_id = order.get("asset_id")
                instrument = order.get("instrument", asset_id)
                action = order.get("side", "NOOP")
                quantity = float(order.get("requested_quantity", 0.0))
                
                # Match executions
                execs = [ex for ex in record.get("executions", []) if ex.get("asset_id") == asset_id]
                exec_price = float(execs[0]["execution_price"]) if execs and execs[0].get("execution_price") is not None else 0.0
                
                dt_state = DecisionTimeState(
                    decision_timestamp=dec_time,
                    instrument=instrument,
                    action=action,
                    quantity=quantity,
                    execution_price=exec_price,
                    portfolio_before=record.get("portfolio_before", {}),
                    portfolio_after=record.get("portfolio_after", {}),
                    state_fingerprint=record.get("state_fingerprint", ""),
                    market_features=record.get("environment_metadata", {}),
                    agent_context_version=record.get("agent_metadata", {}).get("context", "") if record.get("agent_metadata") else None
                )
                
                # Compute Outcomes (Trailing and Forward)
                pre_trend_1d = None
                pre_trend_3d = None
                fwd_return_1d = None
                fwd_return_3d = None
                
                t_minus_1 = self._shift_date(dec_time, -1)
                t_minus_3 = self._shift_date(dec_time, -3)
                t_plus_1 = self._shift_date(dec_time, 1)
                t_plus_3 = self._shift_date(dec_time, 3)
                
                p_t0 = self.lookup.bar_close(asset_id, None, dec_time)
                
                if p_t0 is not None and p_t0 > 0:
                    if t_minus_1:
                        p_t_minus_1 = self.lookup.bar_close(asset_id, None, t_minus_1)
                        if p_t_minus_1 and p_t_minus_1 > 0:
                            pre_trend_1d = (p_t0 - p_t_minus_1) / p_t_minus_1
                    if t_minus_3:
                        p_t_minus_3 = self.lookup.bar_close(asset_id, None, t_minus_3)
                        if p_t_minus_3 and p_t_minus_3 > 0:
                            pre_trend_3d = (p_t0 - p_t_minus_3) / p_t_minus_3
                    if t_plus_1:
                        p_t_plus_1 = self.lookup.bar_close(asset_id, None, t_plus_1)
                        if p_t_plus_1 and p_t_plus_1 > 0:
                            fwd_return_1d = (p_t_plus_1 - p_t0) / p_t0
                    if t_plus_3:
                        p_t_plus_3 = self.lookup.bar_close(asset_id, None, t_plus_3)
                        if p_t_plus_3 and p_t_plus_3 > 0:
                            fwd_return_3d = (p_t_plus_3 - p_t0) / p_t0
                
                outcomes = AttributionOutcomes(
                    pre_trend_1d=pre_trend_1d,
                    pre_trend_3d=pre_trend_3d,
                    forward_return_1d=fwd_return_1d,
                    forward_return_3d=fwd_return_3d,
                    # Optional: compute hold_return, opportunity_return, MAE, MFE based on trace granular data
                )
                
                attr_dec = AttributedDecision(
                    decision_id=f"{episode_id}-{dec_time}-{asset_id}",
                    episode_id=episode_id,
                    arm=arm,
                    decision_time_state=dt_state,
                    outcomes=outcomes
                )
                attributed.append(attr_dec)
                activity_count += 1
                
        return DecisionAttributionResult(
            run_id=run_id,
            experiment_id=experiment_id,
            episode_id=episode_id,
            arm=arm,
            trajectory_fingerprint=trajectory_fingerprint,
            attributed_decisions=attributed,
            activity_count=activity_count
        )
