from pathlib import Path

from src.india.manifest import ManifestManager
from src.schemas.india_data import (
    AcquisitionStatus,
    DataFrequency,
    DataTier,
    ValidationStatus,
)


def test_hash_is_deterministic(tmp_path: Path):
    path = tmp_path / "raw.csv"
    path.write_bytes(b"date,close\n2024-01-01,100\n")
    manager = ManifestManager(tmp_path)
    assert manager.compute_sha256(str(path)) == manager.compute_sha256(str(path))


def test_manifest_round_trip_and_required_fields(tmp_path: Path):
    raw = tmp_path / "raw.csv"
    raw.write_text("date,close\n2024-01-01,100\n")
    manager = ManifestManager(tmp_path)
    created = manager.create_manifest(
        dataset_id="test_index",
        tier=DataTier.A,
        asset_class="index",
        variable="TEST",
        source_institution="NSE",
        frequency=DataFrequency.DAILY,
        source_url="https://example.test/data.csv",
        raw_path="raw.csv",
        earliest_observation="2024-01-01",
        latest_observation="2024-01-01",
        row_count=1,
        acquisition_status=AcquisitionStatus.ACQUIRED,
        validation_status=ValidationStatus.PASSED,
    )
    loaded = manager.load_manifest("test_index")
    assert loaded.raw_sha256 == created.raw_sha256
    assert manager.validate_manifest(loaded) == []


def test_acquired_manifest_without_raw_evidence_is_invalid(tmp_path: Path):
    manager = ManifestManager(tmp_path)
    manifest = manager.create_manifest(
        dataset_id="missing",
        tier=DataTier.A,
        asset_class="index",
        variable="MISSING",
        source_institution="NSE",
        frequency=DataFrequency.DAILY,
        acquisition_status=AcquisitionStatus.ACQUIRED,
    )
    errors = manager.validate_manifest(manifest)
    assert any("raw_path" in error for error in errors)
