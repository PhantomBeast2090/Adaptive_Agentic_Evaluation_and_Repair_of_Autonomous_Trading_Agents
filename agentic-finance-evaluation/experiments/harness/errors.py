"""E3-E harness failure taxonomy (orchestration only, no science).

Every failure here is a fail-closed orchestration signal. Scientific
states (SUCCESS/INCONCLUSIVE/REGRESSION/INVALID/FAILED) keep their
frozen E0–E2 meanings; these errors carry infrastructure and
integrity failures to the harness without converting them.
"""


class HarnessError(Exception):
    """Base class for all harness-orchestration failures."""


class ProtocolAmbiguityError(HarnessError):
    """Runtime configuration demands an unfrozen scientific decision.

    Raised whenever execution would require choosing an endpoint,
    success criterion, regression definition, window, replication
    count, hypothesis, or statistical method not frozen in E3-D.
    The harness fails closed instead of choosing a default.
    """


class IntegrityFailure(HarnessError):
    """A frozen-protocol invariant was violated. Fail closed."""


class ManifestMismatchError(IntegrityFailure):
    """Configuration does not match the frozen E3-C manifest."""


class WindowIntegrityError(IntegrityFailure):
    """Window mismatch, overlap, or scope incompatibility."""


class PoolIntegrityError(IntegrityFailure):
    """Candidate pool or fixed sequence deviates from the manifest."""


class TransitionError(IntegrityFailure):
    """An arm transition outside the allowed lineage graph was attempted."""


class LineageError(IntegrityFailure):
    """A required upstream artefact or identity is missing or mismatched."""


class SealedAccessError(IntegrityFailure):
    """Sealed held-out contents were requested before release."""


class SealIntegrityError(IntegrityFailure):
    """Seal fingerprint mismatch, double release, or wrong-phase release."""


class ProvenanceError(IntegrityFailure):
    """Provenance (git commit, fingerprint, identity) verification failed."""
