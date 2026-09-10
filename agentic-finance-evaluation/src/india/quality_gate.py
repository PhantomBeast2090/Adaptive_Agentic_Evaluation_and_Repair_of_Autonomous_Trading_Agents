"""Experiment-eligibility gates for Indian datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from src.india.leakage_audit import LeakageReport
from src.india.manifest import ManifestManager
from src.schemas.india_data import (
    AcquisitionStatus,
    DatasetManifest,
    EligibilityStatus,
    ValidationStatus,
)


@dataclass
class QualityGateResult:
    dataset_id: str
    eligible: bool
    failed_gates: List[str] = field(default_factory=list)


class DatasetQualityGate:
    """Require provenance, hashes, validation, and leakage cleanliness."""

    def __init__(self, manifest_manager: ManifestManager) -> None:
        self.manifest_manager = manifest_manager

    def evaluate(
        self,
        manifest: DatasetManifest,
        *,
        leakage_report: Optional[LeakageReport] = None,
        temporal_valid: bool = True,
        calendar_valid: bool = True,
        required_fields_valid: bool = True,
        information_available: bool = True,
    ) -> QualityGateResult:
        failures: List[str] = []
        if manifest.acquisition_status != AcquisitionStatus.ACQUIRED:
            failures.append("ACQUIRED")
        if manifest.validation_status != ValidationStatus.PASSED:
            failures.append("SCHEMA_VALID")
        failures.extend(
            f"PROVENANCE_VALID:{error}"
            for error in self.manifest_manager.validate_manifest(manifest)
        )
        if not temporal_valid:
            failures.append("TEMPORAL_VALID")
        if not calendar_valid:
            failures.append("CALENDAR_VALID")
        if not required_fields_valid:
            failures.append("REQUIRED_FIELDS_VALID")
        if not information_available:
            failures.append("INFORMATION_AVAILABILITY_VALID")
        if leakage_report is not None and not leakage_report.is_clean:
            failures.append("LEAKAGE_AUDIT_CLEAN")
        return QualityGateResult(
            dataset_id=manifest.dataset_id,
            eligible=not failures,
            failed_gates=failures,
        )
