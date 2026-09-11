"""Manifest Manager for Indian Market Data.

Provides deterministic SHA-256 hashing, YAML manifest writing/reading,
and manifest validation. Every raw acquisition must produce a manifest.

Raw data is IMMUTABLE research evidence — this module never modifies
raw files, only reads them for hashing.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.schemas.india_data import (
    AcquisitionStatus,
    DataFrequency,
    DataTier,
    DatasetManifest,
    EligibilityStatus,
    ValidationStatus,
)

# Canonical manifests directory relative to the project root
MANIFESTS_DIR = Path("data/manifests/india")


class ManifestError(Exception):
    """Raised when a manifest cannot be created, loaded, or validated."""


class ManifestManager:
    """Create, persist, load, and validate dataset manifests.

    Usage:
        mgr = ManifestManager(base_dir=".")
        sha = mgr.compute_sha256("data/raw/india/indices/nifty50_daily.csv")
        manifest = mgr.create_manifest(
            dataset_id="nse_nifty50_daily",
            tier=DataTier.A,
            asset_class="index",
            variable="NIFTY50_DAILY",
            source_institution="NSE",
            frequency=DataFrequency.DAILY,
            raw_path="data/raw/india/indices/nifty50_daily.csv",
        )
    """

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir).resolve()
        self.manifests_dir = self.base_dir / MANIFESTS_DIR
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def compute_sha256(self, file_path: str) -> str:
        """Compute a deterministic SHA-256 hash of a file.

        Reads in 64KB chunks so large files do not exhaust memory.
        Raw data is never modified.
        """
        path = self._resolve_path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Cannot hash non-existent file: {path}")
        if not path.is_file():
            raise ValueError(f"Path is not a regular file: {path}")

        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def compute_sha256_of_string(self, content: str) -> str:
        """Compute SHA-256 of an in-memory string (UTF-8 encoded)."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_manifest(
        self,
        dataset_id: str,
        tier: DataTier,
        asset_class: str,
        variable: str,
        source_institution: str,
        frequency: DataFrequency,
        source_url: Optional[str] = None,
        raw_path: Optional[str] = None,
        raw_paths: Optional[List[str]] = None,
        raw_artifacts: Optional[List[Dict[str, Any]]] = None,
        processed_path: Optional[str] = None,
        earliest_observation: Optional[str] = None,
        latest_observation: Optional[str] = None,
        row_count: Optional[int] = None,
        unique_date_count: Optional[int] = None,
        duplicate_count: Optional[int] = None,
        has_observation_date: bool = False,
        has_availability_date: bool = False,
        missingness_summary: Optional[List[Dict[str, Any]]] = None,
        validation_status: ValidationStatus = ValidationStatus.PENDING,
        acquisition_status: AcquisitionStatus = AcquisitionStatus.NOT_STARTED,
        processing_version: str = "1.0.0",
        processing_parameters: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        eligibility_status: EligibilityStatus = EligibilityStatus.NOT_STARTED,
    ) -> DatasetManifest:
        """Create a DatasetManifest, compute hashes, and persist to YAML."""
        retrieval_timestamp = datetime.now(timezone.utc).isoformat()

        raw_sha256 = None
        if raw_path is not None:
            try:
                raw_sha256 = self.compute_sha256(raw_path)
            except FileNotFoundError:
                raw_sha256 = None  # File not yet acquired

        if raw_artifacts is None and raw_paths is not None:
            computed: List[Dict[str, Any]] = []
            for candidate in raw_paths:
                try:
                    resolved = self._resolve_path(candidate)
                    computed.append(
                        {
                            "path": candidate,
                            "sha256": self.compute_sha256(candidate),
                            "byte_size": resolved.stat().st_size,
                        }
                    )
                except (FileNotFoundError, OSError, ValueError):
                    computed.append({"path": candidate, "sha256": ""})
            raw_artifacts = computed

        processed_sha256 = None
        if processed_path is not None:
            try:
                processed_sha256 = self.compute_sha256(processed_path)
            except FileNotFoundError:
                processed_sha256 = None

        from src.schemas.india_data import MissingSummaryField, RawArtifactProvenance
        missingness = []
        if missingness_summary:
            for item in missingness_summary:
                if isinstance(item, dict):
                    missingness.append(MissingSummaryField(**item))
                elif isinstance(item, MissingSummaryField):
                    missingness.append(item)

        artifacts = None
        if raw_artifacts is not None:
            artifacts = [
                item if isinstance(item, RawArtifactProvenance)
                else RawArtifactProvenance(**item)
                for item in raw_artifacts
            ]

        manifest = DatasetManifest(
            dataset_id=dataset_id,
            tier=tier,
            asset_class=asset_class,
            variable=variable,
            source_institution=source_institution,
            source_url=source_url,
            retrieval_timestamp=retrieval_timestamp,
            raw_path=raw_path,
            raw_sha256=raw_sha256,
            raw_paths=raw_paths,
            raw_artifacts=artifacts,
            processing_version=processing_version,
            processing_parameters=processing_parameters or {},
            processed_path=processed_path,
            processed_sha256=processed_sha256,
            frequency=frequency,
            earliest_observation=earliest_observation,
            latest_observation=latest_observation,
            row_count=row_count,
            unique_date_count=unique_date_count,
            duplicate_count=duplicate_count,
            has_observation_date=has_observation_date,
            has_availability_date=has_availability_date,
            missingness_summary=missingness,
            validation_status=validation_status,
            acquisition_status=acquisition_status,
            eligibility_status=eligibility_status,
            notes=notes,
        )

        self._persist(manifest)
        return manifest

    # ------------------------------------------------------------------
    # Persist / Load
    # ------------------------------------------------------------------

    def _persist(self, manifest: DatasetManifest) -> Path:
        """Write manifest to YAML. Returns the file path written."""
        output_path = self.manifests_dir / f"{manifest.dataset_id}.yaml"
        yaml_dict = manifest.to_yaml_dict()
        with open(output_path, "w") as f:
            yaml.dump(yaml_dict, f, default_flow_style=False, sort_keys=True)
        return output_path

    def load_manifest(self, dataset_id: str) -> DatasetManifest:
        """Load and parse a manifest by dataset_id."""
        path = self.manifests_dir / f"{dataset_id}.yaml"
        if not path.exists():
            raise ManifestError(f"Manifest not found: {path}")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return DatasetManifest(**data)

    def list_manifests(self) -> List[str]:
        """Return a list of all dataset IDs that have persisted manifests."""
        return sorted(
            p.stem for p in self.manifests_dir.glob("*.yaml")
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_manifest(self, manifest: DatasetManifest) -> List[str]:
        """Validate a manifest for required fields and internal consistency.

        Returns a list of validation error strings. Empty list = valid.
        """
        errors: List[str] = []

        required = DatasetManifest.required_fields()
        for field in required:
            val = getattr(manifest, field, None)
            if val is None or val == "":
                errors.append(f"Required field '{field}' is missing or empty.")

        # If acquired, raw evidence must be present (single- or multi-file).
        if manifest.acquisition_status == AcquisitionStatus.ACQUIRED:
            has_single_raw = bool(manifest.raw_path)
            has_multi_raw = bool(manifest.raw_paths)
            if not has_single_raw and not has_multi_raw:
                errors.append(
                    "Acquired dataset must have raw_path or raw_paths."
                )
            if has_single_raw and not manifest.raw_sha256:
                errors.append("Acquired dataset must have raw_sha256.")
            if has_multi_raw:
                if not manifest.raw_artifacts:
                    errors.append(
                        "Acquired multi-file dataset must record raw_artifacts "
                        "with SHA-256 per file."
                    )
                elif len(manifest.raw_artifacts) != len(manifest.raw_paths or []):
                    errors.append(
                        "raw_artifacts length must match raw_paths length."
                    )
            if not manifest.earliest_observation:
                errors.append("Acquired dataset must have earliest_observation.")
            if not manifest.latest_observation:
                errors.append("Acquired dataset must have latest_observation.")
            if manifest.row_count is None:
                errors.append("Acquired dataset must have row_count.")
            if manifest.source_institution.strip() == "":
                errors.append("Acquired dataset must identify its source institution.")
            if not manifest.source_url and not manifest.notes:
                errors.append(
                    "Acquired dataset must provide a source URL or provenance notes."
                )
            if manifest.raw_path:
                raw = self._resolve_path(manifest.raw_path)
                if not raw.exists():
                    errors.append(f"Acquired raw artifact does not exist: {raw}")
                elif manifest.raw_sha256:
                    actual_hash = self.compute_sha256(str(raw))
                    if actual_hash != manifest.raw_sha256:
                        errors.append(
                            f"Raw SHA-256 mismatch: manifest={manifest.raw_sha256}, "
                            f"actual={actual_hash}."
                        )
            if manifest.raw_paths and manifest.raw_artifacts:
                by_path = {item.path: item.sha256 for item in manifest.raw_artifacts}
                for candidate in manifest.raw_paths:
                    resolved = self._resolve_path(candidate)
                    if not resolved.exists():
                        errors.append(
                            f"Acquired raw artifact does not exist: {resolved}"
                        )
                        continue
                    expected = by_path.get(candidate)
                    if not expected:
                        errors.append(
                            f"Acquired raw artifact missing SHA-256: {candidate}"
                        )
                    elif self.compute_sha256(str(resolved)) != expected:
                        errors.append(
                            f"Raw SHA-256 mismatch: {candidate} "
                            f"manifest={expected}, "
                            f"actual={self.compute_sha256(str(resolved))}."
                        )
            if manifest.processed_path and manifest.processed_sha256:
                processed = self._resolve_path(manifest.processed_path)
                if not processed.exists():
                    errors.append(f"Processed artifact does not exist: {processed}")
                elif self.compute_sha256(str(processed)) != manifest.processed_sha256:
                    errors.append("Processed SHA-256 does not match the artifact.")
        if (
            manifest.eligibility_status == EligibilityStatus.EXPERIMENT_ELIGIBLE
            and manifest.acquisition_status != AcquisitionStatus.ACQUIRED
        ):
            errors.append(
                "Experiment-eligible datasets must have acquisition_status=acquired."
            )

        # Macro / policy data must have availability_date
        if manifest.has_observation_date and not manifest.has_availability_date:
            if manifest.asset_class in ("macro", "policy"):
                errors.append(
                    "Macro/policy datasets must set has_availability_date=True "
                    "and provide availability dates per record."
                )

        # Processed path must differ from raw path(s)
        raw_candidates = []
        if manifest.raw_path:
            raw_candidates.append(manifest.raw_path)
        if manifest.raw_paths:
            raw_candidates.extend(manifest.raw_paths)
        if manifest.processed_path:
            for candidate in raw_candidates:
                if Path(candidate).resolve() == Path(manifest.processed_path).resolve():
                    errors.append(
                        "raw_path and processed_path must be different — "
                        "raw data is immutable and must not be overwritten."
                    )
                    break

        return errors

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            return self.base_dir / p
        return p
