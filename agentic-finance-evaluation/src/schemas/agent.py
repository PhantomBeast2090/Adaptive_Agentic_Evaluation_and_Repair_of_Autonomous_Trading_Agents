from pydantic import BaseModel

class AgentProfile(BaseModel):
    agent_id: str
    agent_version: str
    capability_scores: dict[str, float]
    known_failures: list[str]
    verified_causes: list[str]
    tested_dimensions: list[str]
    untested_dimensions: list[str]
    repair_history: list[str]
    evaluation_history: list[str]