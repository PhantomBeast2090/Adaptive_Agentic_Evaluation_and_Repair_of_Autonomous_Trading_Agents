from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionTimeState(BaseModel):
    """Information explicitly available to the agent at the time of the decision."""
    decision_timestamp: str
    instrument: str
    action: str
    quantity: float
    execution_price: float
    portfolio_before: Dict[str, Any]
    portfolio_after: Dict[str, Any]
    state_fingerprint: str
    market_features: Dict[str, Any]
    agent_context_version: Optional[str] = None


class AttributionOutcomes(BaseModel):
    """Information revealed ONLY AFTER the decision, used exclusively by the evaluator."""
    pre_trend_1d: Optional[float] = None
    pre_trend_3d: Optional[float] = None
    forward_return_1d: Optional[float] = None
    forward_return_3d: Optional[float] = None
    mae: Optional[float] = None
    mfe: Optional[float] = None
    hold_return: Optional[float] = None
    opportunity_return: Optional[float] = None


class AttributedDecision(BaseModel):
    """A single decision deterministically joined with its PIT state and subsequent outcomes."""
    decision_id: str
    episode_id: str
    arm: str
    decision_time_state: DecisionTimeState
    outcomes: AttributionOutcomes


class DecisionAttributionResult(BaseModel):
    """Collection of all attributed decisions for a specific run."""
    run_id: str
    experiment_id: str
    episode_id: str
    arm: str
    trajectory_fingerprint: str
    attributed_decisions: List[AttributedDecision]
    activity_count: int
    created_at: str = Field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
