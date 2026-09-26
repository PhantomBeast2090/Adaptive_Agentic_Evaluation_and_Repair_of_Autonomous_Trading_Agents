"""M2 model abstraction: evaluator-side diagnostic models only.

The rest of the research environment interacts with ML exclusively
through ``BaseModel`` (fit / predict_proba / metadata). TabPFN
internals never leak past the adapter boundary. No model output is a
trading instruction and no model writes to MemoryStore.
"""

from evaluation.ml.models.base import BaseModel

__all__ = ["BaseModel"]
