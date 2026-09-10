"""Base Acquisition Adapter for Indian Market Data.

Every data source adapter must subclass BaseAdapter and implement:
    acquire() → writes raw file(s) to data/raw/india/<subdir>/
    validate() → checks schema compliance and basic quality
    register_manifest() → writes manifest to data/manifests/india/

Contract:
    source → raw artifact → validation → manifest

Network/API failures must raise AcquisitionError with a clear message.
Silent substitution of sources is PROHIBITED.
Silent creation of empty datasets is PROHIBITED.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.india.manifest import ManifestManager
from src.schemas.india_data import (
    AcquisitionStatus,
    DataFrequency,
    DataTier,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


class AcquisitionError(Exception):
    """Raised when a data acquisition fails.

    Contains enough context for the researcher to understand why it failed
    and what manual action (if any) can resolve it.
    """

    def __init__(
        self,
        dataset_id: str,
        source: str,
        reason: str,
        manual_instructions: Optional[str] = None,
    ):
        self.dataset_id = dataset_id
        self.source = source
        self.reason = reason
        self.manual_instructions = manual_instructions
        super().__init__(
            f"[{dataset_id}] Acquisition from {source} failed: {reason}"
            + (
                f"\n\nManual download instructions:\n{manual_instructions}"
                if manual_instructions
                else ""
            )
        )


class ValidationError(Exception):
    """Raised when acquired data fails validation."""


class BaseAdapter(ABC):
    """Abstract base for all Indian market data acquisition adapters.

    Subclasses implement the three-step contract:
        1. acquire()          — fetch/copy raw data
        2. validate()         — verify schema and quality
        3. register_manifest() — write manifest record
    """

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir).resolve()
        self.manifest_mgr = ManifestManager(base_dir=str(self.base_dir))
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def dataset_id(self) -> str:
        """Unique identifier for this dataset (used in manifest filename)."""

    @property
    @abstractmethod
    def tier(self) -> DataTier:
        """Data tier (A, B, or C)."""

    @property
    @abstractmethod
    def asset_class(self) -> str:
        """Asset class string (e.g. 'index', 'equity', 'macro', 'gold')."""

    @property
    @abstractmethod
    def variable(self) -> str:
        """Variable name (e.g. 'NIFTY50_DAILY', 'USD_INR_DAILY')."""

    @property
    @abstractmethod
    def source_institution(self) -> str:
        """Primary source institution (e.g. 'NSE', 'RBI', 'MOSPI', 'MCX')."""

    @property
    @abstractmethod
    def frequency(self) -> DataFrequency:
        """Native data frequency."""

    @property
    @abstractmethod
    def raw_output_dir(self) -> Path:
        """Directory where raw files are written."""

    @abstractmethod
    def acquire(self) -> Path:
        """Download/copy raw data to raw_output_dir.

        Must:
          - Return the path to the written raw file.
          - Raise AcquisitionError if the source is unavailable or blocked.
          - NEVER silently substitute a different source.
          - NEVER create an empty file to fake success.
        """

    @abstractmethod
    def validate(self, raw_path: Path) -> List[str]:
        """Validate the acquired raw data.

        Returns a list of error strings. Empty list = validation passed.
        Must check:
          - File is non-empty
          - Required columns present
          - No completely empty datasets
          - Date column parseable
        """

    def run(self) -> Optional[Path]:
        """Execute the full acquire → validate → manifest pipeline.

        Returns the raw file path on success, None if acquisition status
        is pending_manual_download.
        """
        self.logger.info(f"[{self.dataset_id}] Starting acquisition...")

        # Attempt acquisition
        raw_path: Optional[Path] = None
        acq_status = AcquisitionStatus.NOT_STARTED
        val_status = ValidationStatus.PENDING
        notes = None

        try:
            raw_path = self.acquire()
            acq_status = AcquisitionStatus.ACQUIRED
            self.logger.info(f"[{self.dataset_id}] Acquired → {raw_path}")
        except AcquisitionError as e:
            self.logger.warning(f"[{self.dataset_id}] {e}")
            acq_status = AcquisitionStatus.PENDING_MANUAL_DOWNLOAD
            notes = str(e)
            # Register manifest with pending status and return
            self._register_pending_manifest(acq_status, str(e))
            return None
        except Exception as e:
            self.logger.error(f"[{self.dataset_id}] Unexpected error: {e}")
            acq_status = AcquisitionStatus.ACQUISITION_FAILED
            notes = f"Unexpected error: {e}"
            self._register_pending_manifest(acq_status, notes)
            raise

        # Validate
        errors = self.validate(raw_path)
        if errors:
            val_status = ValidationStatus.FAILED
            self.logger.error(
                f"[{self.dataset_id}] Validation FAILED:\n" +
                "\n".join(f"  - {e}" for e in errors)
            )
        else:
            val_status = ValidationStatus.PASSED
            self.logger.info(f"[{self.dataset_id}] Validation PASSED.")

        metadata = self._manifest_metadata(raw_path)
        self.manifest_mgr.create_manifest(
            dataset_id=self.dataset_id,
            tier=self.tier,
            asset_class=self.asset_class,
            variable=self.variable,
            source_institution=self.source_institution,
            frequency=self.frequency,
            source_url=getattr(self, "source_url", None),
            raw_path=str(raw_path),
            acquisition_status=acq_status,
            validation_status=val_status,
            earliest_observation=metadata["earliest_observation"],
            latest_observation=metadata["latest_observation"],
            row_count=metadata["row_count"],
            unique_date_count=metadata["unique_date_count"],
            duplicate_count=metadata["duplicate_count"],
            has_observation_date=metadata["has_observation_date"],
            has_availability_date=metadata["has_availability_date"],
            notes=notes,
        )

        if val_status == ValidationStatus.FAILED:
            raise ValidationError(
                f"[{self.dataset_id}] Validation failed: {errors}"
            )

        return raw_path

    def _manifest_metadata(self, raw_path: Path) -> Dict[str, Any]:
        """Collect non-destructive coverage metadata for a tabular raw file."""
        metadata: Dict[str, Any] = {
            "earliest_observation": None,
            "latest_observation": None,
            "row_count": None,
            "unique_date_count": None,
            "duplicate_count": None,
            "has_observation_date": False,
            "has_availability_date": False,
        }
        if raw_path.suffix.lower() not in {".csv", ".parquet", ".pq"}:
            return metadata
        frame = (
            pd.read_csv(raw_path)
            if raw_path.suffix.lower() == ".csv"
            else pd.read_parquet(raw_path)
        )
        metadata["row_count"] = len(frame)
        date_col = next(
            (
                column
                for column in (
                    "date",
                    "trade_date",
                    "observation_date",
                    "timestamp",
                )
                if column in frame.columns
            ),
            None,
        )
        if date_col is not None:
            dates = pd.to_datetime(frame[date_col], errors="coerce").dropna()
            if not dates.empty:
                metadata["earliest_observation"] = dates.min().date().isoformat()
                metadata["latest_observation"] = dates.max().date().isoformat()
                metadata["unique_date_count"] = int(dates.nunique())
                metadata["duplicate_count"] = int(dates.duplicated().sum())
        metadata["has_observation_date"] = "observation_date" in frame.columns
        metadata["has_availability_date"] = "availability_date" in frame.columns
        return metadata

    def _register_pending_manifest(
        self, status: AcquisitionStatus, notes: str
    ) -> None:
        self.manifest_mgr.create_manifest(
            dataset_id=self.dataset_id,
            tier=self.tier,
            asset_class=self.asset_class,
            variable=self.variable,
            source_institution=self.source_institution,
            frequency=self.frequency,
            source_url=getattr(self, "source_url", None),
            acquisition_status=status,
            validation_status=ValidationStatus.PENDING,
            notes=notes,
        )

    def _require_non_empty(self, raw_path: Path) -> List[str]:
        """Common validation: file exists and is non-empty."""
        errors = []
        if not raw_path.exists():
            errors.append(f"File does not exist: {raw_path}")
            return errors
        if raw_path.stat().st_size == 0:
            errors.append(f"File is empty (zero bytes): {raw_path}")
        return errors
