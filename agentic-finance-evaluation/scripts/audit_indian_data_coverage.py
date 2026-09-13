#!/usr/bin/env python3
"""Audit acquired Indian datasets without selecting experiment splits.

The auditor intentionally treats a missing or pending dataset as unavailable
evidence.  It never fabricates coverage dates and never forward-fills data.
Run from the project root:

    python scripts/audit_indian_data_coverage.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd
import yaml

# When invoked as ``python scripts/...py``, Python places ``scripts/`` rather
# than the project root on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.india.coverage_audit import CoverageAuditor
from src.india.calendar import load_calendar_directory
from src.india.leakage_audit import LeakageAuditor


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path, encoding="utf-8-sig")
        # Normalize NSE-style headers ("Date ", BOM) without altering values.
        frame.columns = [str(col).lstrip("\ufeff").strip() for col in frame.columns]
        return frame
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".json":
        with path.open() as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and "CBM" in payload:
            records = [
                {**record, "market_segment": str(category)}
                for category, category_records in payload.items()
                if isinstance(category_records, list)
                for record in category_records
                if isinstance(record, dict)
            ]
            return pd.DataFrame(records)
        return pd.DataFrame(payload)
    if suffix == ".txt":
        csv_paths = []
        for line in path.read_text(encoding="utf-8").splitlines():
            candidate = path.parent / line.strip()
            if candidate.suffix.lower() == ".csv" and candidate.exists():
                csv_paths.append(candidate)
        if not csv_paths:
            raise ValueError(f"No listed CSV artifacts found in {path}")
        frames = []
        for item in csv_paths:
            frame = pd.read_csv(item, encoding="utf-8-sig")
            frame.columns = [str(col).lstrip("\ufeff").strip() for col in frame.columns]
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)
    raise ValueError(f"Unsupported tabular artifact: {path.suffix}")


def _resolve_raw_evidence(
    manifest: dict[str, Any], base_dir: Path
) -> tuple[list[Path], Optional[Path]]:
    """Return (existing raw files, processed file if present).

    Supports both legacy single-file manifests (``raw_path``) and the
    multi-file extension (``raw_paths`` + ``raw_artifacts``) without
    rewriting raw evidence.
    """
    raw_files: list[Path] = []
    raw_value = manifest.get("raw_path")
    if raw_value:
        candidate = (
            Path(raw_value)
            if Path(raw_value).is_absolute()
            else base_dir / str(raw_value)
        )
        if candidate.exists():
            raw_files.append(candidate)
        elif manifest.get("acquisition_status") == "acquired":
            # Single-file manifest claims acquisition but file is missing.
            pass
    for entry in manifest.get("raw_paths") or []:
        candidate = (
            Path(entry) if Path(entry).is_absolute() else base_dir / str(entry)
        )
        if candidate.exists():
            raw_files.append(candidate)
    processed_value = manifest.get("processed_path")
    processed: Optional[Path] = None
    if processed_value:
        candidate = (
            Path(processed_value)
            if Path(processed_value).is_absolute()
            else base_dir / str(processed_value)
        )
        if candidate.exists():
            processed = candidate
    return raw_files, processed


def _date_column(df: pd.DataFrame) -> Optional[str]:
    normalized = {
        str(col).lstrip("\ufeff").strip(): col for col in df.columns
    }
    lowered = {key.lower(): value for key, value in normalized.items()}
    for candidate in (
        "date",
        "trade_date",
        "trading_date",
        "observation_date",
        "timestamp",
        "datetime",
        "tradingdate",
    ):
        if candidate in lowered:
            return lowered[candidate]
    return None


def _manifest_files(manifest_dir: Path) -> Iterable[Path]:
    return sorted(manifest_dir.glob("*.yaml")) + sorted(manifest_dir.glob("*.yml"))


def _load_manifests(manifest_dir: Path) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in _manifest_files(manifest_dir):
        with path.open() as handle:
            value = yaml.safe_load(handle) or {}
        value["_manifest_path"] = str(path)
        manifests.append(value)
    return manifests


def _required_dataset_ids(base_dir: Path) -> list[str]:
    config_path = base_dir / "configs" / "india_data.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return [str(item) for item in config.get("required_datasets", [])]


def _identifier_cols(asset_class: Any) -> list[str] | None:
    """Identifier grain per asset class (dates repeat legitimately in
    security/contract/policy datasets; duplicates are evaluated on the
    identifier grain, never on bare dates)."""
    if asset_class == "calendar":
        return ["market_segment"]
    if asset_class == "gold":
        return ["contract_symbol", "expiry_date"]
    if asset_class == "equity":
        # Security x date grain: repeated dates across securities are
        # legitimate; duplicates are evaluated on (date, symbol, series).
        return ["symbol", "series"]
    if asset_class == "policy":
        return ["rate_type"]
    return None


def _markdown_result(result: Any, *, calendar_membership: bool = False) -> list[str]:
    duplicate_timestamps = (
        "not applicable (category membership)"
        if calendar_membership
        else str(result.temporal.duplicate_timestamps)
    )
    lines = [
        f"### `{result.dataset_id}`",
        f"- Earliest: `{result.temporal.earliest or 'n/a'}`",
        f"- Latest: `{result.temporal.latest or 'n/a'}`",
        f"- Observations: {result.temporal.total_observations}",
        f"- Unique dates: {result.temporal.unique_dates}",
        f"- Duplicate timestamps: {duplicate_timestamps}",
        f"- Duplicate identifier pairs: {result.temporal.duplicate_identifier_pairs}",
    ]
    if result.missingness:
        lines.append("- Missingness:")
        for item in result.missingness:
            lines.append(
                f"  - `{item.field_name}`: {item.missing_count}/{item.total_count} "
                f"({item.missing_pct:.2f}%)"
            )
    if result.consistency.gaps_detected:
        lines.append(
            f"- Temporal gaps above threshold: {len(result.consistency.gaps_detected)}"
        )
    if result.calendar:
        lines.append(
            f"- Calendar: {result.calendar.non_trading_day_observations} "
            f"non-trading observations; {result.calendar.missing_trading_days} "
            f"heuristic trading days absent ({result.calendar.checked_against})"
        )
    if result.availability:
        lines.append(
            f"- Availability violations: {result.availability.violations}/"
            f"{result.availability.total_records}"
        )
    for note in result.notes:
        if calendar_membership and note.startswith("WARNING: ") and "duplicate timestamps" in note:
            continue
        lines.append(f"- Note: {note}")
    if calendar_membership:
        lines.append(
            "- Note: Repeated dates are legitimate market-segment membership; "
            "duplicate records are evaluated by `(market_segment, trading_date)`."
        )
    return lines


def run_audit(base_dir: Path) -> str:
    manifest_dir = base_dir / "data" / "manifests" / "india"
    auditor = CoverageAuditor()
    calendar = load_calendar_directory(
        base_dir / "data" / "raw" / "india" / "indices"
    )
    acquired: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    errors: list[str] = []

    for manifest in _load_manifests(manifest_dir):
        status = str(manifest.get("acquisition_status", "not_started")).lower()
        raw_files, processed_file = _resolve_raw_evidence(manifest, base_dir)
        dataset_label = str(manifest.get("dataset_id", "unknown"))
        if status != "acquired" or not raw_files:
            pending.append(manifest)
            continue
        # Prefer the canonical processed artifact when present (it carries
        # deduplicated, chronologically sorted observations with a stable
        # `date` column). Raw annual files remain the immutable evidence and
        # are hash-verified via the manifest.
        audit_path: Optional[Path] = processed_file
        try:
            if audit_path is not None:
                df = _read_table(audit_path)
            else:
                frames = [_read_table(item) for item in raw_files]
                df = (
                    pd.concat(frames, ignore_index=True)
                    if len(frames) > 1
                    else frames[0]
                )
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            errors.append(f"{dataset_label}: {exc}")
            continue

        date_col = _date_column(df)
        if date_col is None:
            errors.append(
                f"{dataset_label}: no supported date column"
            )
            continue

        required = [
            item.get("field_name")
            for item in manifest.get("missingness_summary", [])
            if isinstance(item, dict) and item.get("field_name")
        ]
        audit_stem = (
            audit_path.stem
            if audit_path is not None
            else (raw_files[0].stem if raw_files else dataset_label)
        )
        dataset_id = str(manifest.get("dataset_id", audit_stem))
        frequency = str(manifest.get("frequency", "")).lower()
        frequency = frequency.rsplit(".", 1)[-1]
        is_event_based = frequency == "event_based"
        frequency = {"daily": "daily", "monthly": "monthly"}.get(frequency)
        is_trading = manifest.get("asset_class") not in {"macro", "policy", "calendar"}
        identifier_cols = _identifier_cols(manifest.get("asset_class"))
        result = auditor.audit_dataset(
            dataset_id=dataset_id,
            df=df,
            required_fields=required,
            date_col=date_col,
            expected_frequency=frequency,
            # Event-based policy decisions are sparse by nature; routine
            # inter-event intervals are not temporal gaps.
            max_gap_days=400 if is_event_based else 10,
            is_trading_day_data=is_trading,
            has_availability_date=bool(manifest.get("has_availability_date")),
            allow_pre_observation=manifest.get("asset_class") == "policy",
            calendar=calendar,
            identifier_cols=identifier_cols,
        )
        acquired.append({"manifest": manifest, "result": result, "df": df})

    mandatory = _required_dataset_ids(base_dir)
    eligible = {
        item["manifest"]["dataset_id"]
        for item in acquired
        if str(item["manifest"].get("eligibility_status", "")).lower()
        == "experiment_eligible"
    }
    observed_dates = [
        set(
            pd.to_datetime(item["df"][_date_column(item["df"])])
            .dropna()
            .dt.date
        )
        for item in acquired
        if _date_column(item["df"]) is not None
    ]
    session_dates = set().union(*observed_dates) if observed_dates else None
    auditor_session_dates = session_dates
    # Re-run availability-aware usability against the actual candidate sessions.
    # The re-run must preserve the identifier grain (and policy semantics);
    # otherwise it would overwrite the stored result with a bare-date
    # evaluation and misrepresent identifier coverage.
    if auditor_session_dates:
        for item in acquired:
            manifest = item["manifest"]
            if manifest.get("has_availability_date"):
                date_col = _date_column(item["df"])
                auditor.audit_dataset(
                    dataset_id=item["result"].dataset_id,
                    df=item["df"],
                    required_fields=[
                        field.get("field_name")
                        for field in manifest.get("missingness_summary", [])
                        if isinstance(field, dict) and field.get("field_name")
                    ],
                    date_col=date_col,
                    expected_frequency=None,
                    is_trading_day_data=manifest.get("asset_class")
                    not in {"macro", "policy", "calendar"},
                    has_availability_date=True,
                    allow_pre_observation=manifest.get("asset_class") == "policy",
                    calendar=calendar,
                    identifier_cols=_identifier_cols(manifest.get("asset_class")),
                    session_dates=auditor_session_dates,
                )
    intersection = auditor.compute_common_intersection(
        mandatory_datasets=mandatory,
        eligible_datasets=eligible,
    )
    price_frames = [
        item["df"]
        for item in acquired
        if item["manifest"].get("asset_class")
        in {"equity", "index", "volatility", "volatility_index", "currency", "fixed_income"}
    ]
    macro_frames = [
        item["df"]
        for item in acquired
        if item["manifest"].get("asset_class") == "macro"
    ]
    policy_frames = [
        item["df"]
        for item in acquired
        if item["manifest"].get("asset_class") == "policy"
    ]
    gold_frames = [
        item["df"]
        for item in acquired
        if item["manifest"].get("asset_class") == "gold"
    ]
    processing_parameters = {
        item["manifest"]["dataset_id"]: item["manifest"].get(
            "processing_parameters", {}
        )
        for item in acquired
        if item["manifest"].get("processing_parameters")
        and item["manifest"].get("asset_class") != "calendar"
    }
    leakage = LeakageAuditor().audit_all(
        price_df=pd.concat(price_frames, ignore_index=True)
        if price_frames
        else None,
        macro_df=pd.concat(macro_frames, ignore_index=True)
        if macro_frames
        else None,
        policy_df=pd.concat(policy_frames, ignore_index=True)
        if policy_frames
        else None,
        gold_contracts_df=pd.concat(gold_frames, ignore_index=True)
        if gold_frames
        else None,
        processing_parameters=processing_parameters or None,
    )
    lines = [
        "# Indian Data Coverage Audit",
        "",
        "> Generated from acquired artifacts and manifests. This report does not",
        "> freeze context, discovery, re-evaluation, or OOD experiment dates.",
        "",
        "## 1. Acquisition status",
        "",
        f"- Acquired and auditable datasets: **{len(acquired)}**",
        f"- Acquired mandatory market/macro datasets: **{sum(item['manifest'].get('asset_class') != 'calendar' for item in acquired)}**",
        f"- Acquired support/calendar artifacts: **{sum(item['manifest'].get('asset_class') == 'calendar' for item in acquired)}**",
        f"- Pending/unavailable datasets: **{len(pending)}**",
        f"- Artifact read errors: **{len(errors)}**",
    ]
    if not acquired and not pending:
        lines.append(
            "- No dataset manifests exist yet; inventory entries without manifests "
            "are not treated as acquired or assigned coverage."
        )
    if pending:
        lines.append("- Pending datasets:")
        for item in pending:
            lines.append(
                f"  - `{item.get('dataset_id', 'unknown')}`: "
                f"{item.get('acquisition_status', 'not_started')} — "
                f"{item.get('notes', 'no manifest notes')}"
            )
    if errors:
        lines.append("- Read errors:")
        lines.extend(f"  - {error}" for error in errors)

    lines.extend(["", "## 2. Dataset-by-dataset coverage", ""])
    if acquired:
        for item in acquired:
            manifest = item["manifest"]
            raw_hash_lines = []
            if manifest.get("raw_paths") and manifest.get("raw_artifacts"):
                raw_hash_lines.append(
                    f"- Raw artifacts: `{len(manifest['raw_paths'])} annual files`"
                )
                for artifact in manifest["raw_artifacts"]:
                    if isinstance(artifact, dict):
                        raw_hash_lines.append(
                            f"  - `{artifact.get('path')}`: "
                            f"`{artifact.get('sha256', 'not recorded')}`"
                        )
            else:
                raw_hash_lines.append(
                    f"- Raw SHA-256: `{manifest.get('raw_sha256', 'not recorded')}`"
                )
            if manifest.get("processed_path"):
                raw_hash_lines.append(
                    f"- Processed: `{manifest.get('processed_path')}` "
                    f"SHA-256 `{manifest.get('processed_sha256', 'not recorded')}`"
                )
            lines.extend([
                f"- Source: `{manifest.get('source_institution', 'unknown')}`",
                *raw_hash_lines,
            ])
            lines.extend(
                _markdown_result(
                    item["result"],
                    calendar_membership=manifest.get("asset_class") == "calendar",
                )
            )
            lines.append("")
    else:
        lines.append("No acquired datasets were found; no empirical coverage exists yet.")

    lines.extend(
        [
            "## 3. Missingness",
            "",
            "Missingness is reported per required field above. No values were "
            "forward-filled by this audit.",
            "",
            "## 4. Duplicate analysis",
            "",
            "Duplicate timestamps and date/identifier pairs are reported per dataset above.",
            "",
            "## 5. Calendar analysis",
            "",
            "Trading-day checks use the versioned NSE holiday artifact when its "
            "coverage includes the audited years. Years outside that artifact are "
            "reported as calendar-unavailable rather than inferred from weekdays.",
            "",
            "## 6. Information-availability analysis",
            "",
            "Macro and policy datasets must carry observation_date and availability_date. "
            "Values are not eligible for agent observations before availability_date.",
            "",
            "## 7. Common intersection",
            "",
            f"- Status: **{intersection.status}**",
            f"- Earliest common usable date: `{intersection.earliest_common or 'not computable'}`",
            f"- Latest common usable date: `{intersection.latest_common or 'not computable'}`",
            f"- Calendar duration: {intersection.total_common_days} days",
            f"- Datasets included: {', '.join(intersection.included_datasets) or 'none'}",
            f"- Datasets excluded: {', '.join(intersection.excluded_datasets) or 'none'}",
            f"- Jointly usable sessions: {intersection.total_common_days}",
            f"- Limiting datasets: {', '.join(intersection.limiting_datasets) or 'none'}",
        ]
    )
    if intersection.exclusion_reasons:
        lines.append("- Exclusion reasons:")
        lines.extend(
            f"  - `{name}`: {reason}"
            for name, reason in intersection.exclusion_reasons.items()
        )
    lines.extend(
        [
            "",
            "## 8. Data-quality blockers",
            "",
            *(
                [f"- {error}" for error in errors]
                or ["- No artifact read errors were encountered."]
            ),
            "",
            "## 9. Leakage findings",
            "",
            f"- Leakage validation status: **{leakage.validation_status}**",
            f"- Datasets checked: {', '.join(leakage.datasets_checked) or 'none'}",
            f"- Confirmed leaks: {len(leakage.confirmed_leaks)}",
            f"- Potential leaks: {len(leakage.potential_leaks)}",
            f"- Mitigated issues: {len(leakage.mitigated)}",
            f"- Unresolved issues: {len(leakage.unresolved)}",
            "- Gold futures must remain contract-level until a roll method is "
            "selected and independently audited.",
            "",
            "## 10. Recommended next methodological decision",
            "",
            "Complete official-source acquisition and release-date verification for "
            "the mandatory datasets. Then review this audit to define the longest "
            "clean common period before selecting any temporal split boundaries.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional report path (defaults to INDIAN_DATA_COVERAGE_AUDIT.md).",
    )
    args = parser.parse_args()
    base_dir = args.base_dir.resolve()
    output = args.output or base_dir / "INDIAN_DATA_COVERAGE_AUDIT.md"
    output.write_text(run_audit(base_dir), encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
