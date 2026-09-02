from pydantic import BaseModel
from typing import Optional, Any

class Scenario(BaseModel):
    scenario_id: str
    source: str
    dimension: str
    difficulty: str
    market_regime: str
    information_state: Any
    task: str
    constraints: list[str]
    ground_truth: Any
    expected_behaviour: str
    holdout: bool