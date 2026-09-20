"""E3-E experimental harness (execution orchestration, no science).

Coordinates frozen E0–E2 primitives under the frozen E3-D protocol:
manifest-verified configuration, deterministic identity, arm/lineage
guards, sealed held-out baselines, phased lifecycle, preflight
dry-runs, and immutable result artefacts. The harness computes no
metrics, runs no statistics, and makes no scientific decisions —
ambiguity fails closed via ``ProtocolAmbiguityError``.
"""

from experiments.harness.config import ARMS, ExperimentConfig
from experiments.harness.errors import (
    HarnessError,
    IntegrityFailure,
    LineageError,
    ManifestMismatchError,
    ProtocolAmbiguityError,
    ProvenanceError,
    SealIntegrityError,
    SealedAccessError,
    TransitionError,
    WindowIntegrityError,
)
from experiments.harness.identity import (
    arm_identity,
    experiment_identity,
    result_path,
)
from experiments.harness.lineage import (
    ASSEMBLY_PHASE,
    SealedBaseline,
    assert_same_scope,
    assert_transition,
    heldout_scope,
    require_repair_lineage,
    require_rh_lineage,
)
from experiments.harness.result import (
    RQ4_DESCRIPTIVE_ONLY,
    ExperimentResult,
    RQ4Status,
)

__all__ = [
    "ARMS",
    "ASSEMBLY_PHASE",
    "ExperimentConfig",
    "ExperimentResult",
    "HarnessError",
    "IntegrityFailure",
    "LineageError",
    "ManifestMismatchError",
    "ProtocolAmbiguityError",
    "ProvenanceError",
    "RQ4_DESCRIPTIVE_ONLY",
    "RQ4Status",
    "SealIntegrityError",
    "SealedAccessError",
    "SealedBaseline",
    "TransitionError",
    "WindowIntegrityError",
    "arm_identity",
    "assert_same_scope",
    "assert_transition",
    "experiment_identity",
    "heldout_scope",
    "require_repair_lineage",
    "require_rh_lineage",
    "result_path",
]
