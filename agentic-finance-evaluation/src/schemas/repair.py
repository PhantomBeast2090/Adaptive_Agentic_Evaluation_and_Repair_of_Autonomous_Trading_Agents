from pydantic import BaseModel

class RepairRecord(BaseModel):
    failure_id: str
    root_cause: str
    repair_type: str
    old_agent_version: str
    new_agent_version: str
    expected_effect: str
    actual_effect: str
    validation_result: str
    regression_result: str