"""E4 validated context learning (additive; E0–E3 untouched)."""

from evaluation.context.extraction import (
    EXTRACTION_METHOD,
    EXTRACTION_VERSION,
    extract_candidate,
)
from evaluation.context.gate import (
    GATE_METHOD,
    GATE_VERSION,
    AdmissionDecision,
    AdmissionVerdict,
    adjudicate,
)
from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.context.memory import (
    STORE_METHOD,
    STORE_VERSION,
    MemoryStore,
    StoredEntry,
)

__all__ = [
    "EXTRACTION_METHOD",
    "EXTRACTION_VERSION",
    "GATE_METHOD",
    "GATE_VERSION",
    "STORE_METHOD",
    "STORE_VERSION",
    "AdmissionDecision",
    "AdmissionVerdict",
    "ContextStatus",
    "LearnedContext",
    "MemoryStore",
    "StoredEntry",
    "adjudicate",
    "extract_candidate",
]
