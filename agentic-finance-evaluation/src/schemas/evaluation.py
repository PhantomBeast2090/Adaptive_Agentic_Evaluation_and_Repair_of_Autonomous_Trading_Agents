from pydantic import BaseModel
from typing import Any

class EvaluationResult(BaseModel):
    run_id: str
    agent_version: str
    scenario_id: str
    evaluator_id: str
    score: float
    failure: bool
    severity: str
    evidence: str
    confidence: float
    cost: float
    latency: float
    timestamp: str