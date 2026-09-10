from pathlib import Path

from src.india.leakage_audit import LeakageReport
from src.india.manifest import ManifestManager
from src.india.quality_gate import DatasetQualityGate
from src.schemas.india_data import (
    AcquisitionStatus,
    DataFrequency,
    DataTier,
    ValidationStatus,
)


def test_quality_gate_requires_clean_leakage_and_provenance(tmp_path: Path):
    raw = tmp_path / "raw.csv"
    raw.write_text("date,close\n2024-01-01,100\n")
    manager = ManifestManager(tmp_path)
    manifest = manager.create_manifest(
        dataset_id="quality",
        tier=DataTier.A,
        asset_class="index",
        variable="X",
        source_institution="NSE",
        source_url="https://example.test/x.csv",
        frequency=DataFrequency.DAILY,
        raw_path="raw.csv",
        earliest_observation="2024-01-01",
        latest_observation="2024-01-01",
        row_count=1,
        acquisition_status=AcquisitionStatus.ACQUIRED,
        validation_status=ValidationStatus.PASSED,
    )
    clean = LeakageReport([], [], [], [])
    result = DatasetQualityGate(manager).evaluate(manifest, leakage_report=clean)
    assert result.eligible is True


def test_quality_gate_rejects_unresolved_leakage(tmp_path: Path):
    manager = ManifestManager(tmp_path)
    manifest = manager.create_manifest(
        dataset_id="pending",
        tier=DataTier.A,
        asset_class="index",
        variable="X",
        source_institution="NSE",
        source_url="https://example.test/x.csv",
        frequency=DataFrequency.DAILY,
    )
    report = LeakageReport([], [], [], [])
    result = DatasetQualityGate(manager).evaluate(
        manifest, leakage_report=report, calendar_valid=False
    )
    assert result.eligible is False
    assert "ACQUIRED" in result.failed_gates
    assert "CALENDAR_VALID" in result.failed_gates


def test_quality_gate_requires_explicit_macro_information_timing(tmp_path: Path):
    manager = ManifestManager(tmp_path)
    manifest = manager.create_manifest(
        dataset_id="macro",
        tier=DataTier.C,
        asset_class="macro",
        variable="CPI",
        source_institution="MOSPI",
        source_url="https://example.test/cpi.csv",
        frequency=DataFrequency.MONTHLY,
    )
    result = DatasetQualityGate(manager).evaluate(
        manifest,
        leakage_report=LeakageReport([], [], [], []),
    )
    assert result.eligible is False
    assert "INFORMATION_AVAILABILITY_VALID" in result.failed_gates
