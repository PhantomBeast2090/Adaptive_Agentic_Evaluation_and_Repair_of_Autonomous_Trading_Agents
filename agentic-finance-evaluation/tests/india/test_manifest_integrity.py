from pathlib import Path

from src.india.manifest import ManifestManager
from src.schemas.india_data import AcquisitionStatus, DataFrequency, DataTier, ValidationStatus


def test_manifest_detects_stale_raw_hash(tmp_path: Path):
    raw = tmp_path / "raw.csv"
    raw.write_text("x\n1\n")
    manager = ManifestManager(tmp_path)
    manifest = manager.create_manifest(
        dataset_id="stale",
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
    raw.write_text("x\n2\n")
    assert any("SHA-256 mismatch" in error for error in manager.validate_manifest(manifest))
