"""E4 validated context learning (additive; E0–E3 untouched)."""

from evaluation.context.assembly import (
    ASSEMBLY_METHOD,
    ASSEMBLY_VERSION,
    DELIVERY_METHOD,
    DELIVERY_VERSION,
    ContextPackage,
    DeliveryRecord,
    assemble,
    deliver,
)
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
from evaluation.context.retrieval import (
    RETRIEVAL_METHOD,
    RETRIEVAL_VERSION,
    RetrievalRecord,
    retrieve,
)

__all__ = [
    "ASSEMBLY_METHOD",
    "ASSEMBLY_VERSION",
    "DELIVERY_METHOD",
    "DELIVERY_VERSION",
    "EXTRACTION_METHOD",
    "EXTRACTION_VERSION",
    "GATE_METHOD",
    "GATE_VERSION",
    "RETRIEVAL_METHOD",
    "RETRIEVAL_VERSION",
    "STORE_METHOD",
    "STORE_VERSION",
    "AdmissionDecision",
    "AdmissionVerdict",
    "ContextPackage",
    "ContextStatus",
    "DeliveryRecord",
    "LearnedContext",
    "MemoryStore",
    "RetrievalRecord",
    "StoredEntry",
    "adjudicate",
    "assemble",
    "deliver",
    "extract_candidate",
    "retrieve",
]
