"""Phase-3 adaptive experiment provenance schemas.

Follows the Phase-2 static-evaluation schema conventions (pydantic,
serializable, auditable). Records everything needed to reproduce and compare
a paired Adaptive-vs-Random run: configuration snapshot, fingerprints,
ordered scenario sequence, selection scores/reasons, and discovery evidence.

No diagnosis, repair, or LLM reasoning belongs here (Phase 4+ excluded).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SelectionRecord(BaseModel):
    """Why one scenario was selected at one step."""

    step: int
    scenario_id: str
    phase: str  # "initial" | "selection"
    strategy: str  # "adaptive" | "random"
    rank: Optional[int] = None
    score: Optional[float] = None
    reason: str = ""
    contributing_vulns: List[str] = []
    contributing_categories: List[str] = []
    market_regime: Optional[str] = None
    difficulty: Optional[str] = None


class AdaptiveRunRecord(BaseModel):
    """Persisted provenance for one Adaptive or Random arm."""

    run_id: str
    experiment_id: str
    description: str = ""
    strategy: str  # "adaptive" | "random"
    seed: int
    agent_id: str
    agent_version: str
    agent_class: str = ""
    agent_module: str = ""
    budget: int
    initial_samples: int
    batch_size: int
    dataset_fingerprint: str = ""
    pool_fingerprint: str = ""
    pool_size: int = 0
    scenario_sequence: List[str] = []
    selection_history: List[SelectionRecord] = []
    episode_evaluations: List[Dict[str, Any]] = []
    vulnerabilities: List[Dict[str, Any]] = []
    vulnerability_categories: List[str] = []
    evaluated_count: int = 0
    unique_vulnerabilities: int = 0
    git_commit: str = "unknown"
    configuration: Dict[str, Any] = {}
    timestamp: str = Field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
