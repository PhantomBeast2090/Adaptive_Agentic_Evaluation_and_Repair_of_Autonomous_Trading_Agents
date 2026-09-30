"""Mechanism-relative normality specifications for M-R7 (additive).

A NormalitySpecification answers one question: for a given diagnostic
session record, is the behaviour protected from repair alteration?
Three frozen specifications compare regime-protected (N0), mechanism-
relative (N1), and hybrid (N2) normality for the diagnosed exposure
mechanism. Inputs are PIT-safe session fields plus the frozen mechanism
diagnosis only — never candidate outcomes, economics, or held-out data
(enforced by signature: no such argument exists; pinned by AST tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from evaluation.contracts.fingerprints import fingerprint_of_dict

SPEC_VERSION = "v1"


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return fingerprint_of_dict(dict(payload))


@dataclass(frozen=True)
class NormalitySpecification:
    """Frozen protected-session predicate for one normality definition."""

    specification_id: str
    version: str
    description: str
    required_fields: tuple
    kind: str

    def __post_init__(self) -> None:
        for name in ("specification_id", "version", "description",
                     "kind"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.kind not in ("regime", "mechanism", "hybrid"):
            raise ValueError(
                f"kind must be regime/mechanism/hybrid, got {self.kind!r}")
        object.__setattr__(
            self, "required_fields", tuple(self.required_fields))

    def protected_session(
        self,
        record: Mapping[str, Any],
        mechanism: str,
    ) -> bool:
        """True iff the session behaviour is protected from alteration.

        Inputs: one adapted diagnostic session (PIT-safe fields) and the
        frozen mechanism taxonomy string. Calm regime reads the ``vix``
        field against the frozen 25.0 band; mechanism activity reads the
        ``exposure_active`` flag precomputed from the frozen diagnosis
        (breadth above the detector's normal bound). Missing fields fail
        closed (protected), never open.
        """
        if self.kind == "regime":
            vix = record.get("vix")
            if not isinstance(vix, (int, float)) or isinstance(vix, bool):
                return True
            return vix <= 25.0
        if self.kind == "mechanism":
            active = record.get("exposure_active")
            if not isinstance(active, bool):
                return True
            return not active
        active = record.get("exposure_active")
        if not isinstance(active, bool):
            return True
        vix = record.get("vix")
        if not isinstance(vix, (int, float)) or isinstance(vix, bool):
            return True
        return vix <= 25.0 and not active

    def audit(self) -> dict:
        return {
            "specification_id": self.specification_id,
            "version": self.version,
            "description": self.description,
            "required_fields": list(self.required_fields),
            "kind": self.kind,
            "fingerprint": self.fingerprint(),
        }

    def fingerprint(self) -> str:
        return _fingerprint({
            "specification_id": self.specification_id,
            "version": self.version,
            "description": self.description,
            "required_fields": list(self.required_fields),
            "kind": self.kind,
        })


N0_REGIME_PROTECTED = NormalitySpecification(
    specification_id="N0",
    version=SPEC_VERSION,
    description="M-R6 regime-protected normality: calm VIX sessions "
                "(vix <= 25.0) are protected irrespective of mechanism "
                "activity. Control: reproduces the M-R6 adjudication.",
    required_fields=("vix",),
    kind="regime",
)

N1_MECHANISM_RELATIVE = NormalitySpecification(
    specification_id="N1",
    version=SPEC_VERSION,
    description="Mechanism-relative normality: behaviour is protected "
                "exactly when the diagnosed exposure mechanism is "
                "absent (breadth within the detector normal bound). "
                "Market regime alone never protects.",
    required_fields=("exposure_active",),
    kind="mechanism",
)

N2_HYBRID = NormalitySpecification(
    specification_id="N2",
    version=SPEC_VERSION,
    description="Regime x mechanism normality: protected only when the "
                "market is calm (vix <= 25.0) AND the exposure mechanism "
                "is absent. Conservative hybrid.",
    required_fields=("vix", "exposure_active"),
    kind="hybrid",
)

SPECIFICATIONS = {
    "N0": N0_REGIME_PROTECTED,
    "N1": N1_MECHANISM_RELATIVE,
    "N2": N2_HYBRID,
}


def annotate_exposure_active(
    sessions: list,
    max_normal_names: int,
) -> list:
    """Attach the frozen mechanism-activity flag (breadth diagnosis).

    A session is exposure-active iff names_held exceeds the detector's
    frozen normal bound. Deterministic; diagnostic data only.
    """
    annotated = []
    for row in sessions:
        flagged = dict(row)
        try:
            held = int(row.get("names_held", 0) or 0)
        except (TypeError, ValueError):
            held = 0
        flagged["exposure_active"] = held > max_normal_names
        annotated.append(flagged)
    return annotated
