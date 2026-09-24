"""E4 validated context learning (additive; E0–E3 untouched)."""

from evaluation.context.extraction import (
    EXTRACTION_METHOD,
    EXTRACTION_VERSION,
    extract_candidate,
)
from evaluation.context.learned import ContextStatus, LearnedContext

__all__ = [
    "EXTRACTION_METHOD",
    "EXTRACTION_VERSION",
    "ContextStatus",
    "LearnedContext",
    "extract_candidate",
]
