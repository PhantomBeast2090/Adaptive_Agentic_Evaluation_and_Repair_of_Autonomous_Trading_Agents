from pathlib import Path

from src.india.manifest import ManifestManager


def test_hashing_does_not_modify_raw_file(tmp_path: Path):
    raw = tmp_path / "raw.csv"
    raw.write_text("date,close\n2024-01-01,100\n")
    before = raw.read_bytes()
    ManifestManager(tmp_path).compute_sha256(str(raw))
    assert raw.read_bytes() == before


def test_raw_and_processed_paths_must_differ(tmp_path: Path):
    raw = tmp_path / "raw.csv"
    raw.write_text("x\n1\n")
    manager = ManifestManager(tmp_path)
    manifest = manager.create_manifest(
        dataset_id="same_path",
        tier="A",
        asset_class="index",
        variable="X",
        source_institution="NSE",
        frequency="daily",
        raw_path=str(raw),
        processed_path=str(raw),
    )
    assert any("different" in error for error in manager.validate_manifest(manifest))
