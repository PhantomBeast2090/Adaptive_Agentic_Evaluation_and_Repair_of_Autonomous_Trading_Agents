"""MoSPI CPI Combined General index (2012=100) monthly canonicalization.

Official source: Ministry of Statistics and Programme Implementation (MoSPI),
National Statistics Office (NSO) monthly CPI press releases (base 2012=100).

Raw evidence (immutable, under ``data/raw/india/macro/cpi/``):
  - One MoSPI press-release PDF per recovered reference month. Each release
    states its reference month, its release (Dated) date, the provisional
    Combined General index for the reference month and the final Combined
    General index for the previous month (genuine provisional -> final
    vintage structure; revisions are preserved, never overwritten).
  - ``CPI_Dec2025.pdf`` (Dec-2025 release, Jan-2026): Annexure VI time series
    of All-India General CPI Combined since January 2013 — the values
    backbone for the homogeneous 2012=100 window.
  - ``CPI_Jan2026_first2024base.pdf``: supporting evidence carrying the
    December-2025 FINAL 2012-base Combined value (198.0).
  - Four PIB-mirrored MoSPI releases for Jul-Oct 2025 (MoSPI UUID URLs not
    recoverable; content is the MoSPI release, mirrored by PIB). The Aug-2025
    PIB publication carries a PIB "Posted On" timestamp used as release
    evidence with a distinct availability basis.
  - Twenty-three base-2010 press releases (2011-2014, ``t4_*`` plus two
    ``cpi_pr_*`` transition files) kept as semantic evidence of series
    history. Their values are NOT canonicalized (pre-homogeneous base).

Homogeneity: All-India CPI Combined General index, base 2012=100,
January 2013 - December 2025 (156 months). The 2011-2012 back series and
the 2010-base old series are excluded (no self-created splicing or
rescaling). The 2024-base series (from Jan-2026) is excluded. Index-only;
no YoY inflation column (derivable later).

Temporal semantics (per the Indian Data Contract):
  - observation_period: YYYY-MM reference month; observation_date: month-end.
  - availability_date: verified release date (MoSPI Dated header, PIB posting
    where noted, or the documented 2015-02-12 revision release for 2013-2014
    back-series values whose contemporaneous releases were base-2010).
  - Months without verifiable release timing keep availability NULL and are
    machine-excluded from any agent-facing InformationSet (fail closed).

No interpolation, no forward-fill, no inferred release dates.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

RAW_SUBDIR = "cpi"
BACKBONE_FILE = "CPI_Dec2025.pdf"
JAN26_SUPPORT_FILE = "CPI_Jan2026_first2024base.pdf"
REVISION_RELEASE_FILE = "cpi_pr_12feb15t.pdf"
REVISION_RELEASE_DATE = date(2015, 2, 12)
HOMOGENEOUS_START = (2013, 1)
HOMOGENEOUS_END = (2025, 12)

CANONICAL_COLUMNS = [
    "observation_period",
    "observation_date",
    "availability_date",
    "cpi_index",
    "vintage_status",
    "revision_version",
    "availability_basis",
    "source",
    "source_files",
]

AGENT_ELIGIBLE_VINTAGES = frozenset(
    {"provisional", "final", "revision_back_series", "imputed"}
)

MONTH_NAME_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

MONTH_ABBR_TO_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

GENERAL_INDEX_PATTERN = re.compile(
    r"General Index \(All Groups\)\s+100\.00\s+([\d.]+)\s+([\d.]+)"
    r"\s+100\.00\s+([\d.]+)\s+([\d.]+)\s+100\.00\s+([\d.]+)\s+([\d.]+)"
)
# COVID-era compact layout: one (index, inflation) pair per sector, the
# index column being the reference-month provisional value, e.g.
# "General Index (All Groups) 100.00 152.5 6.20 100.00 150.5 5.91
#  100.00 151.6 6.09" (June-2020 release, Annex I provisional-only table).
COMPACT_INDEX_PATTERN = re.compile(
    r"General Index \(All Groups\)\s+100\.00\s+([\d.]+)\s+([\d.]+)"
    r"\s+100\.00\s+([\d.]+)\s+([\d.]+)\s+100\.00\s+([\d.]+)\s+([\d.]+)"
)
# Imputed lockdown values, e.g. "General Index (All Groups) 100.00
# 151.9 @ 151.2 @ 100.00 ..." with note "@ : Index imputed for April
# and May 2020" (June-2020 release, Annex II).
IMPUTED_INDEX_PATTERN = re.compile(
    r"General Index \(All Groups\)\s+100\.00\s+([\d.]+)\s*@\s*([\d.]+)\s*@"
    r"\s+100\.00\s+([\d.]+)\s*@\s*([\d.]+)\s*@\s+100\.00\s+([\d.]+)"
    r"\s*@\s*([\d.]+)\s*@"
)
REF_PATTERN = re.compile(
    r"FOR THE MONTH OF\s+([A-Za-z]+)[,\s]+(20\d\d)", re.IGNORECASE
)
DATED_PATTERN = re.compile(
    r"Dated?\s+(?:the\s+)?(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*,?\s*(20\d\d)"
)
POSTED_PATTERN = re.compile(
    r"Posted On:\s*(\d{1,2})\s+([A-Za-z]{3})\s+(20\d\d)"
)
ANNEX_VI_TABLE_PATTERN = re.compile(
    r"Year Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec (.*)", re.DOTALL
)
ANNEX_VI_ROW_PATTERN = re.compile(r"(20\d\d)\s+((?:[\d.]+\s*){1,12})")


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_cpi_raw_files(raw_dir: Path) -> List[Path]:
    """Return sorted MoSPI CPI raw files (PDFs + PIB HTML pages).

    Raw files are never modified.
    """
    return sorted(list(raw_dir.glob("*.pdf")) + list(raw_dir.glob("*.html")))


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def read_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def detect_base(normalized: str) -> Optional[str]:
    has12 = "BASE 2012" in normalized
    has10 = "BASE 2010" in normalized
    if has12 and not has10:
        return "2012"
    if has10 and not has12:
        return "2010"
    if has12 and has10:
        return "2012+2010"
    return None


@dataclass
class CpiReleaseEvidence:
    filename: str
    ref_year: int
    ref_month: int
    release_date: Optional[date]
    release_basis: str
    base: Optional[str]
    comb_prev_final: Optional[float] = None
    comb_prov: Optional[float] = None


def extract_general_combined(normalized: str) -> Optional[Tuple[float, ...]]:
    """Extract (rural_prev, rural_prov, urban_prev, urban_prov, comb_prev,
    comb_prov) from the Annexure I index table.

    Several tables mention 'General Index (All Groups)' (index levels and
    inflation rates). Index values on base 2012=100 for 2013+ are always
    >= 50 while inflation rates are single/double digits, so candidates
    containing any value < 50 are rejected and the next occurrence tried.
    Returns None when only the COVID-era compact provisional table exists
    (use extract_compact_provisional instead).
    """
    for match in GENERAL_INDEX_PATTERN.finditer(normalized):
        values = tuple(float(match.group(i)) for i in range(1, 7))
        if all(value >= 50 for value in values):
            return values
    return None


def extract_compact_provisional(normalized: str) -> Optional[Tuple[float, float, float]]:
    """Extract (rural_prov, urban_prov, comb_prov) from a COVID-era compact
    Annex I table carrying one (index, inflation) pair per sector.

    Accepted only when each pair splits cleanly into an index (>= 50) and
    an inflation rate (< 50); otherwise None.
    """
    for match in COMPACT_INDEX_PATTERN.finditer(normalized):
        pairs = [(float(match.group(i)), float(match.group(i + 1)))
                 for i in (1, 3, 5)]
        if all(index >= 50 and infl < 50 for index, infl in pairs):
            return (pairs[0][0], pairs[1][0], pairs[2][0])
    return None


def extract_imputed_apr_may_2020(normalized: str) -> Optional[Dict[str, float]]:
    """Extract imputed Combined General indices for April/May 2020 from the
    June-2020 release Annex II ('@ : Index imputed for April and May 2020').

    Returns {'2020-04': value, '2020-05': value} or None.
    """
    if "imputed for April and May 2020" not in normalized:
        return None
    match = IMPUTED_INDEX_PATTERN.search(normalized)
    if not match:
        return None
    return {"2020-04": float(match.group(5)), "2020-05": float(match.group(6))}


def parse_release_pdf(path: Path) -> CpiReleaseEvidence:
    """Parse one press-release PDF into dated vintage evidence.

    Raises ValueError when the reference month cannot be established.
    The release date may legitimately be None (unrecoverable timing);
    such evidence is preserved but can never enter the agent set.
    """
    text = read_pdf_text(path)
    normalized = re.sub(r"\s+", " ", text)
    ref = REF_PATTERN.search(normalized)
    if not ref:
        raise ValueError(f"{path.name}: reference month not found")
    ref_month = MONTH_NAME_TO_NUM[ref.group(1).strip().lower()]
    ref_year = int(ref.group(2))
    release_date: Optional[date] = None
    basis = "unverified"
    dated = DATED_PATTERN.search(normalized)
    if dated:
        release_date = date(
            int(dated.group(3)),
            MONTH_NAME_TO_NUM[dated.group(2).strip().lower()],
            int(dated.group(1)),
        )
        basis = "mospi_press_release"
    else:
        posted = POSTED_PATTERN.search(normalized)
        if posted:
            abbr = posted.group(2).strip().lower()
            if abbr in MONTH_ABBR_TO_NUM:
                release_date = date(
                    int(posted.group(3)),
                    MONTH_ABBR_TO_NUM[abbr],
                    int(posted.group(1)),
                )
                basis = "pib_posting"
    gen = extract_general_combined(normalized)
    compact_prov: Optional[float] = None
    if gen is None:
        compact = extract_compact_provisional(normalized)
        if compact is not None:
            compact_prov = compact[2]
    return CpiReleaseEvidence(
        filename=path.name,
        ref_year=ref_year,
        ref_month=ref_month,
        release_date=release_date,
        release_basis=basis,
        base=detect_base(normalized),
        comb_prev_final=gen[4] if gen else None,
        comb_prov=gen[5] if gen else compact_prov,
    )


def parse_pib_release_html(path: Path) -> CpiReleaseEvidence:
    """Parse a PIB release page (HTML) for a CPI month whose MoSPI PDF is
    unrecoverable (e.g. Aug-2025, whose mirrored PDF has corrupted text
    spacing). PIB is the Government of India's official dissemination
    record: values come from the release tables and the release date from
    the 'Posted On' timestamp, recorded under availability basis
    'pib_posting'. Raises ValueError when the tables cannot be found.
    """
    html = path.read_text(encoding="utf-8", errors="replace")
    ref = re.search(
        r"FOR THE MONTH OF\s+([A-Za-z]+)[,\s]+(20\d\d)", html, re.IGNORECASE
    )
    if not ref:
        raise ValueError(f"{path.name}: reference month not found")
    posted = re.search(
        r"Posted On[^0-9]*(\d{1,2})\s+([A-Za-z]{3})\s+(20\d\d)", html
    )
    if not posted:
        raise ValueError(f"{path.name}: PIB posting timestamp not found")
    anchor = html.find("Monthly changes (%) in All India CPI (General)")
    if anchor < 0:
        raise ValueError(f"{path.name}: monthly-changes table not found")
    segment = re.sub(r"<[^>]+>", "|", html[anchor:anchor + 20000])
    segment = re.sub(r"\|+", "|", segment)
    values: Optional[Tuple[float, ...]] = None
    for row in re.finditer(r"CPI \(General\)", segment):
        floats = [float(number) for number in
                  re.findall(r"\d+\.\d+", segment[row.end():row.end() + 500])]
        if len(floats) >= 6 and all(50 <= v <= 400 for v in floats[:6]):
            values = tuple(floats[:6])
            break
    if values is None:
        raise ValueError(f"{path.name}: CPI General row not found")
    # PIB monthly-changes layout per row: (rural_prov, urban_prov,
    # comb_prov, rural_final, urban_final, comb_final) — provisional triple
    # first, unlike MoSPI PDF Annexure I ((prev, prov) per sector).
    return CpiReleaseEvidence(
        filename=path.name,
        ref_year=int(ref.group(2)),
        ref_month=MONTH_NAME_TO_NUM[ref.group(1).strip().lower()],
        release_date=date(
            int(posted.group(3)),
            MONTH_ABBR_TO_NUM[posted.group(2).strip().lower()],
            int(posted.group(1)),
        ),
        release_basis="pib_posting",
        base="2012",
        comb_prev_final=values[5],
        comb_prov=values[2],
    )


def parse_dec2025_final_from_jan26(path: Path) -> Tuple[float, date]:
    """Extract the December-2025 FINAL Combined General index (2012=100)
    carried by the first 2024-base release (Jan-2026, dated 2026-02-12).

    Returns (value, release_date). Raises ValueError if not found.
    """
    normalized = re.sub(r"\s+", " ", read_pdf_text(path))
    section = re.search(
        r"December,? 2025 \(Final\) at Base 2012=100(.*?)III\.", normalized,
        re.DOTALL,
    )
    if not section:
        raise ValueError(f"{path.name}: Dec-2025 final section not found")
    match = re.search(
        r"Index\s+CPI \(General\)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
        section.group(1),
    )
    if not match:
        raise ValueError(f"{path.name}: Dec-2025 final index row not found")
    return float(match.group(3)), date(2026, 2, 12)


def parse_annex_vi_series(text: str) -> Dict[Tuple[int, int], float]:
    """Parse the Annexure VI year x month Combined General index table."""
    normalized = re.sub(r"\s+", " ", text)
    table = ANNEX_VI_TABLE_PATTERN.search(normalized)
    if not table:
        raise ValueError("Annexure VI time-series table not found")
    body = table.group(1)
    # The table ends where Annexure VII (inflation rates) begins.
    vii = re.search(r"Annexure VII", body)
    if vii:
        body = body[:vii.start()]
    series: Dict[Tuple[int, int], float] = {}
    for year_text, values_text in ANNEX_VI_ROW_PATTERN.findall(body):
        values = values_text.split()
        if len(values) != 12:
            raise ValueError(f"Annex VI row {year_text} has {len(values)} values")
        for month, value in enumerate(values, start=1):
            series[(int(year_text), month)] = float(value)
    return series


@dataclass
class CpiExcludedFile:
    filename: str
    reason: str


@dataclass
class CpiConflict:
    observation_period: str
    detail: str


def build_canonical(
    evidences: List[CpiReleaseEvidence],
    annex_series: Dict[Tuple[int, int], float],
    backbone_file: str,
    extra_vintages: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[pd.DataFrame, List[CpiExcludedFile], List[CpiConflict]]:
    """Combine release vintages with the Annexure VI backbone.

    Rules (never interpolate, never infer dates):
      - Provisional (rev 0) and final (rev 1) vintages from parsed PDFs.
      - Annexure VI cross-check: a parsed final must match the backbone
        within 0.011; a parsed provisional within 0.6 (provisional may
        legitimately revise). Larger deviations are conflicts: the vintage
        is blocked, evidence preserved.
      - Months with no parsed vintage: one backbone row, availability NULL
        (agent-ineligible), except 2013-2014 which carry the documented
        2015-02-12 revision-release availability.
      - Exact (period, value, availability, status) duplicates from
        re-uploaded PDFs are deduplicated with provenance merged.
    """
    excluded: List[CpiExcludedFile] = []
    conflicts: List[CpiConflict] = []
    rows: List[Dict[str, Any]] = []

    by_ref: Dict[Tuple[int, int], List[CpiReleaseEvidence]] = {}
    for evidence in evidences:
        if evidence.base != "2012":
            excluded.append(
                CpiExcludedFile(
                    filename=evidence.filename,
                    reason=(
                        "non-homogeneous base "
                        f"({evidence.base}); pre-2015 base-2010 release, "
                        "values not canonicalized"
                    ),
                )
            )
            continue
        by_ref.setdefault((evidence.ref_year, evidence.ref_month), []).append(evidence)

    def period_text(year: int, month: int) -> str:
        return f"{year:04d}-{month:02d}"

    def in_window(year: int, month: int) -> bool:
        return bool(HOMOGENEOUS_START <= (year, month) <= HOMOGENEOUS_END)

    # Provenance per logical vintage so re-uploaded PDFs merge file lists
    # instead of losing evidence to deduplication.
    provenance: Dict[tuple, List[str]] = {}

    def add_row(row: Dict[str, Any], filename: str) -> None:
        key = (row["observation_period"], row["cpi_index"],
               str(row["availability_date"]), row["vintage_status"])
        bucket = provenance.setdefault(key, [])
        if filename not in bucket:
            bucket.append(filename)
        if len(bucket) == 1:
            rows.append(row)

    for (year, month), items in sorted(by_ref.items()):
        if not in_window(year, month):
            for item in items:
                excluded.append(
                    CpiExcludedFile(
                        filename=item.filename,
                        reason=f"reference {period_text(year, month)} outside "
                        "homogeneous 2013-01..2025-12 window",
                    )
                )
            continue
        for item in items:
            if item.release_date is None:
                excluded.append(
                    CpiExcludedFile(
                        filename=item.filename,
                        reason=f"reference {period_text(year, month)} without "
                        "recoverable release date; values preserved in raw "
                        "evidence only",
                    )
                )
                continue
            if item.comb_prov is None:
                continue
            add_row(
                {
                    "observation_period": period_text(year, month),
                    "observation_date": month_end(year, month),
                    "availability_date": item.release_date,
                    "cpi_index": item.comb_prov,
                    "vintage_status": "provisional",
                    "revision_version": 0,
                    "availability_basis": item.release_basis,
                    "source": "MOSPI",
                    "source_files": item.filename,
                },
                item.filename,
            )
    # Final vintages arrive via the NEXT month's release. This is driven
    # per evidence (not per referenced month) so a month keeps its final
    # vintage even when it has no release of its own (e.g. 2020-02 whose
    # final comes from the March-2020 release).
    for item in evidences:
        if item.base != "2012":
            continue
        if item.release_date is None or item.comb_prev_final is None:
            continue
        prev_year, prev_month = (
            (item.ref_year, item.ref_month - 1)
            if item.ref_month > 1 else (item.ref_year - 1, 12)
        )
        if not in_window(prev_year, prev_month):
            continue
        if not in_window(item.ref_year, item.ref_month):
            continue
        add_row(
            {
                "observation_period": period_text(prev_year, prev_month),
                "observation_date": month_end(prev_year, prev_month),
                "availability_date": item.release_date,
                "cpi_index": item.comb_prev_final,
                "vintage_status": "final",
                "revision_version": 1,
                "availability_basis": item.release_basis,
                "source": "MOSPI",
                "source_files": item.filename,
            },
            item.filename,
        )
        # Backbone cross-check for this month's vintages is performed in
        # the consolidated pass below (after extra vintages are merged).

    # Backbone-only months (no parsed vintage at all).
    covered = {r["observation_period"] for r in rows}
    for extra in extra_vintages or []:
        key = (extra["observation_period"], extra["cpi_index"],
               str(extra["availability_date"]), extra["vintage_status"])
        if key in {(r["observation_period"], r["cpi_index"],
                    str(r["availability_date"]), r["vintage_status"])
                   for r in rows}:
            continue
        rows.append(dict(extra))
        covered.add(extra["observation_period"])
    for (year, month), value in sorted(annex_series.items()):
        period = period_text(year, month)
        if period in covered:
            continue
        if not (HOMOGENEOUS_START <= (year, month) <= HOMOGENEOUS_END):
            continue
        if (year, month) < (2015, 1):
            rows.append(
                {
                    "observation_period": period,
                    "observation_date": month_end(year, month),
                    "availability_date": REVISION_RELEASE_DATE,
                    "cpi_index": value,
                    "vintage_status": "revision_back_series",
                    "revision_version": 0,
                    "availability_basis": "revision_back_series_2015",
                    "source": "MOSPI",
                    "source_files": f"{backbone_file};{REVISION_RELEASE_FILE}",
                }
            )
        else:
            rows.append(
                {
                    "observation_period": period,
                    "observation_date": month_end(year, month),
                    "availability_date": None,
                    "cpi_index": value,
                    "vintage_status": "final_series_only",
                    "revision_version": 0,
                    "availability_basis": "unverified",
                    "source": "MOSPI",
                    "source_files": backbone_file,
                }
            )

    frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    # Consolidated backbone cross-check: finals must match the backbone
    # within 0.011; provisionals/imputed within 0.6 (genuine revision room).
    # Larger deviations are conflicts: vintage blocked, evidence preserved.
    for row in rows:
        period = row["observation_period"]
        year_m, month_m = int(period[:4]), int(period[5:7])
        backbone_value = annex_series.get((year_m, month_m))
        if backbone_value is None:
            continue
        tolerance = 0.011 if row["vintage_status"] == "final" else 0.6
        if abs(row["cpi_index"] - backbone_value) > tolerance:
            conflicts.append(
                CpiConflict(
                    observation_period=period,
                    detail=(
                        f"{row['vintage_status']}={row['cpi_index']} "
                        f"deviates from Annexure VI={backbone_value} "
                        f"({row['source_files']})"
                    ),
                )
            )
    # Deterministic ordering + merged provenance. Rows are unique by
    # construction (add_row dedupes); source_files merges re-uploaded PDFs
    # via the provenance map. Backbone-only and extra rows keep theirs.
    if not frame.empty:
        frame["_avail_key"] = frame["availability_date"].astype(str)

        def merged_sources(row: Any) -> str:
            key = (row["observation_period"], row["cpi_index"],
                   row["_avail_key"], row["vintage_status"])
            if key in provenance and len(provenance[key]) > 1:
                return ";".join(sorted(provenance[key]))
            return str(row["source_files"])

        frame["source_files"] = frame.apply(merged_sources, axis=1)
        frame = frame.drop(columns=["_avail_key"])
        frame["observation_date"] = pd.to_datetime(
            frame["observation_date"]).dt.date
        frame["availability_date"] = pd.to_datetime(
            frame["availability_date"], errors="coerce").dt.date
        frame = frame.sort_values(
            ["observation_date", "revision_version"]).reset_index(drop=True)
    return frame[CANONICAL_COLUMNS], excluded, conflicts


def agent_eligible_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return only rows with verified availability for agent-facing use."""
    eligible = frame[
        frame["availability_date"].notna()
        & frame["vintage_status"].isin(AGENT_ELIGIBLE_VINTAGES)
    ].copy()
    return eligible.reset_index(drop=True)


def build_agent_information_set(frame: pd.DataFrame):
    """Build an InformationSet of agent-eligible CPI vintages.

    Fails closed when nothing is eligible. Retrospective macro rule
    applies: availability must not precede the observation month-end.
    """
    from src.india.information_set import InformationSet

    eligible = agent_eligible_rows(frame)
    if eligible.empty:
        raise ValueError("No agent-eligible CPI vintages.")
    vintages = pd.DataFrame({
        "variable": "CPI_COMBINED",
        "observation_date": pd.to_datetime(eligible["observation_date"]),
        "availability_date": pd.to_datetime(eligible["availability_date"]),
        "revision_version": eligible["revision_version"].astype(int),
        "value": eligible["cpi_index"].astype(float),
    })
    return InformationSet(vintages)


def validate_no_forward_fill(frame: pd.DataFrame) -> List[str]:
    """Confirm canonical months are never fabricated: every row traces to a
    parsed PDF vintage or the Annexure VI backbone month itself."""
    errors: List[str] = []
    for period, group in frame.groupby("observation_period"):
        if group["cpi_index"].isna().any():
            errors.append(f"{period}: null cpi_index")
        if (group["cpi_index"] <= 0).any():
            errors.append(f"{period}: non-positive cpi_index")
    return errors
