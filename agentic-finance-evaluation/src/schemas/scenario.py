from pydantic import BaseModel, Field
from typing import Optional, Any, List
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Scenario(BaseModel):
    scenario_id: str
    source: str
    dimension: str
    difficulty: str
    market_regime: str
    information_state: Any
    task: str
    constraints: List[str]
    ground_truth: Any
    expected_behaviour: str
    holdout: bool


class StaticScenario(BaseModel):
    """Extended scenario for static evaluation with data split configuration."""
    scenario_id: str
    source_split: str  # "context" | "discovery" | "re_evaluation" | "ood_validation"
    market_data_path: str
    start_date: str
    end_date: str
    dimension: str  # "performance" | "risk" | "decision_quality" | "constraint" | "robustness" | "consistency" | "safety"
    difficulty: str  # "easy" | "medium" | "hard"
    market_regime: str  # "bull" | "bear" | "volatile" | "stable" | "mixed"
    initial_cash: float
    transaction_cost_bps: float
    holdout: bool
    description: str
    created_at: str = Field(default_factory=_utc_now_iso)