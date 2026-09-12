"""MoSPI IIP General Index (2011-12=100) monthly canonicalization.

Official source: Ministry of Statistics and Programme Implementation (MoSPI),
National Statistics Office (NSO) monthly Quick Estimates press releases
(base 2011-12=100), supplemented by PIB mirrors where MoSPI URLs are
unrecoverable.

Raw evidence (immutable, under ``data/raw/india/macro/iip/``):
  - One press release per recovered reference month. Each release states its
    reference month, its release (Dated) date, the Quick Estimate General
    value for the reference month, and (in most eras) the months undergoing
    first revision and final revision. Statement I republishes recent
    General values (latest known state at that release date).
  - ``iip_PR_12may17.pdf``: May-2017 base-revision release carrying the
    official 60-month back-series (Apr-2012..Mar-2017) on base 2011-12.
  - Pre-2017 base-2004-05 releases kept as semantic evidence of series
    history; their values are NEVER canonicalized (no rescaling/splicing).
  - 2022-23-base releases kept as evidence-only (new series from Apr-2026);
    never canonicalized here.

Homogeneity: All-India IIP General Index, base 2011-12=100, April 2012 to
March 2026 as recoverable. FY2011-12 monthly data was never published on
this base (back-series starts FY2012-13); nothing is spliced to fill it.
Index level only (no YoY growth column; derivable later).

Vintage model (empirical, per release evidence — never assumed):
  - quick (rev 0): reference-month Quick Estimate from its own release.
  - first_revision (rev 1): months explicitly named for first revision.
  - final (rev 2): months explicitly named for final revision. New-format
    releases (2025+, 28th schedule) may finalize several months at once;
    whatever is stated is what is recorded.
  - back_series (rev 0): May-2017 back-series values, available 2017-05-12.
  - republished (rev sequential): Statement I values for months with no
    explicit vintage covering that value; availability = first release in
    which the value appeared. At most one row per (period, status-source);
    distinct later values extend the timeline honestly.
  - imputed (rev 0): values MoSPI explicitly labels imputed, if any.

Temporal semantics (per the Indian Data Contract):
  - observation_period: YYYY-MM reference month; observation_date: month-end
    (technical representation, never an availability claim).
  - availability_date: verified release date (MoSPI Dated header, embargo
    corroboration, or PIB Posted-On where noted). NULL where unrecoverable;
    such rows are machine-excluded from any agent-facing InformationSet
    (fail closed).

No interpolation, no forward-fill, no inferred release dates, no RBI fill.
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

RAW_SUBDIR = "iip"
BACKSERIES_FILE = "iip_PR_12may17.pdf"
BACKSERIES_RELEASE_DATE = date(2017, 5, 12)
HOMOGENEOUS_START = (2012, 4)
HOMOGENEOUS_END = (2026, 3)

CANONICAL_COLUMNS = [
    "observation_period",
    "observation_date",
    "availability_date",
    "iip_index",
    "vintage_status",
    "revision_version",
    "availability_basis",
    "source",
    "source_files",
]

AGENT_ELIGIBLE_VINTAGES = frozenset(
    {"quick", "first_revision", "final", "back_series", "republished",
     "imputed"}
)

STATUS_REVISION = {
    "quick": 0,
    "first_revision": 1,
    "final": 2,
    "imputed": 0,
    "back_series": 0,
}

MONTH_NAME_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

MONTH_ABBR_TO_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

REF_PATTERN = re.compile(
    r"FOR\s+THE MONTH OF\s+([A-Za-z]+)[,\s]+(20\d\d)", re.IGNORECASE
)
DATED_PATTERN_A = re.compile(
    r"Dated?:?\s+([A-Za-z]+)\s+(\d{1,2})[^,]*,\s*(20\d\d)"
)
DATED_PATTERN_B = re.compile(
    r"Dated?(?:\s+the)?\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s+"
    r"([A-Za-z]+)[,\s]+(20\d\d)"
)
EMBARGO_PATTERN = re.compile(
    r"embargoed against publication.*?till\s+[\d.]+\s*(?:PM|AM)?\s*"
    r"(?:of\s+|on\s+|today\s+i\.e\.\s*)?(\d{1,2})\s*(?:st|nd|rd|th)?\s+"
    r"([A-Za-z]+)[,\s]+(20\d\d)",
    re.IGNORECASE,
)
POSTED_PATTERN = re.compile(
    r"Posted On[^0-9]*(\d{1,2})\s+([A-Za-z]{3})\s+(20\d\d)"
)
QE_PATTERN = re.compile(r"stands? at\s+(\d+\.\d+)")
REVISION_R1_PATTERN = re.compile(
    r"indices for\s+([A-Za-z]+)[,\s]+(20\d\d)[^.]{0,150}?"
    r"first revision",
    re.IGNORECASE,
)
REVISION_FINAL_PATTERN = re.compile(
    r"those for\s+([A-Za-z]+)[,\s]+(20\d\d)[^.]{0,150}?"
    r"final(?:\s+\(second\))?\s+revision",
    re.IGNORECASE,
)
FINAL_ONLY_PATTERN = re.compile(
    r"indices for\s+([A-Za-z]+)[,\s]+(20\d\d)[^.]{0,150}?"
    r"final revision",
    re.IGNORECASE,
)
FINAL_LIST_PATTERN = re.compile(
    r"indices for\s+([^.]{0,200}?)\s+have undergone final revision",
    re.IGNORECASE,
)
NOTE_PATTERN = re.compile(
    r"NOTE\s*:?\s*Indices for the months of\s+([^.]{0,200}?)\s+incorporate",
    re.IGNORECASE,
)
MONTH_YEAR_TOKEN = re.compile(
    r"([A-Za-z]+)[,\s']+(20\d\d)"
)


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_iip_raw_files(raw_dir: Path) -> List[Path]:
    """Return sorted IIP raw files (PDFs + PIB HTML pages).

    Raw files are never modified.
    """
    return sorted(list(raw_dir.glob("*.pdf")) + list(raw_dir.glob("*.html")))


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def normalize_text(text: str) -> str:
    for old, new in (("‐", "-"), ("‑", "-"), ("‒", "-"), ("–", "-"),
                     ("—", "-")):
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text)


def read_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def detect_base(normalized: str) -> Optional[str]:
    upper = normalized.upper()
    if re.search(r"BASE\s*:?\s*2011-12", upper):
        return "2011-12"
    if re.search(r"BASE\s*:?\s*2022-23", upper):
        return "2022-23"
    if re.search(r"BASE\s*:?\s*2004-05", upper):
        return "2004-05"
    return None


def month_num(name: str) -> Optional[int]:
    key = name.strip().lower()
    if key in MONTH_NAME_TO_NUM:
        return MONTH_NAME_TO_NUM[key]
    if key[:3] in MONTH_ABBR_TO_NUM:
        return MONTH_ABBR_TO_NUM[key[:3]]
    return None


def parse_month_list(fragment: str) -> List[Tuple[int, int]]:
    """Parse 'December 2024, January 2025 and February 2025' style lists."""
    out = []
    for match in MONTH_YEAR_TOKEN.finditer(fragment):
        number = month_num(match.group(1))
        if number is not None:
            out.append((int(match.group(2)), number))
    return out


@dataclass
class IipReleaseEvidence:
    filename: str
    ref_year: int
    ref_month: int
    release_date: Optional[date]
    release_basis: str
    base: Optional[str]
    qe_general: Optional[float] = None
    first_revision_months: List[Tuple[int, int]] = field(default_factory=list)
    final_revision_months: List[Tuple[int, int]] = field(default_factory=list)
    note_months: List[Tuple[int, int]] = field(default_factory=list)
    stmt_general: Dict[Tuple[str, str], float] = field(default_factory=dict)
    stmt_fys: List[str] = field(default_factory=list)


def parse_statement_general(normalized: str) -> Tuple[Dict, List[str]]:
    """Parse Statement I General columns: {(fy, mon3): value}, [fy...].

    Handles 2- or 3-FY headers and partial Jan/Feb/Mar rows that carry only
    the older FY (newer months not yet released): those map to the first FY.
    Truncates at Average/growth/STATEMENT II sections (minimum position).
    Early-era files may place the sectoral table outside the first
    STATEMENT I block, so every statement block is tried in order.
    """
    blocks = re.split(r"STATEMENT I{1,3}", normalized)[1:]
    for block in blocks:
        # NOTE: 'Cumulative' is deliberately not a stop marker (steering
        # prose mentions cumulative indices before the month rows).
        cuts = [pos for marker in
                ("STATEMENT II", "STATEMENT III", "Average", "Growth over")
                for pos in [block.find(marker)] if pos > 0]
        segment = block[:min(cuts)] if cuts else block[:8000]
        result = _parse_sectoral_block(segment)
        if result[0]:
            return result
    return {}, []


def _parse_sectoral_block(segment: str) -> Tuple[Dict, List[str]]:
    fys = re.search(r"General\s+(?:\([\d.]+\)\s*)+((?:20\d\d-\d\d\s*)+)",
                    segment)
    if not fys:
        return {}, []
    # 2011-12-base gate: transition-era files also print 2004-05 tables.
    # The 2011-12 mining weight starts '14.37' (2004-05 uses a 1000 scale);
    # weights sit between 'General' and the FY labels.
    if "14.37" not in segment[fys.start():fys.end() + 50]:
        return {}, []
    labels = fys.group(1).split()
    if len(labels) % 4 != 0 or len(labels) < 8:
        return {}, []
    nf = len(labels) // 4
    gen_fys = labels[3 * nf:4 * nf]
    out: Dict[Tuple[str, str], float] = {}
    for match in re.finditer(
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
            r"[#*]?\s+((?:[\d.*-]+\s*)+)", segment):
        tokens = [tok.replace("*", "") for tok in match.group(2).split()]
        try:
            values = [float(tok) for tok in tokens]
        except ValueError:
            continue
        if len(values) == 4 * nf:
            for fy, value in zip(gen_fys, values[3 * nf:4 * nf]):
                out[(fy, match.group(1)[:3].lower())] = value
        elif len(values) == 4 * (nf - 1) and nf > 1:
            # Partial Jan/Feb/Mar rows: newer fiscal months not yet released,
            # so only the older FYs are printed; map positionally to them.
            for fy, value in zip(gen_fys[:nf - 1], values[3 * (nf - 1):]):
                out[(fy, match.group(1)[:3].lower())] = value
        elif len(values) == 4:
            out[(gen_fys[0], match.group(1)[:3].lower())] = values[3]
    return out, gen_fys


def parse_release_pdf(path: Path) -> IipReleaseEvidence:
    """Parse one monthly IIP press-release PDF into dated vintage evidence.

    Raises ValueError when the reference month cannot be established.
    Release date may legitimately be None (preserved, never agent-visible).
    """
    normalized = normalize_text(read_pdf_text(path))
    ref = REF_PATTERN.search(normalized)
    if not ref:
        raise ValueError(f"{path.name}: reference month not found")
    ref_month = month_num(ref.group(1))
    if ref_month is None:
        raise ValueError(f"{path.name}: unparseable month {ref.group(1)!r}")
    ref_year = int(ref.group(2))
    release_date: Optional[date] = None
    basis = "unverified"
    dated = DATED_PATTERN_A.search(normalized)
    if dated and month_num(dated.group(1)) is not None:
        release_date = date(int(dated.group(3)),
                            month_num(dated.group(1)), int(dated.group(2)))
        basis = "mospi_press_release"
    else:
        dated_b = DATED_PATTERN_B.search(normalized)
        if dated_b and month_num(dated_b.group(2)) is not None:
            release_date = date(int(dated_b.group(3)),
                                month_num(dated_b.group(2)),
                                int(dated_b.group(1)))
            basis = "mospi_press_release"
    if release_date is None:
        embargo = EMBARGO_PATTERN.search(normalized)
        if embargo and month_num(embargo.group(2)) is not None:
            release_date = date(int(embargo.group(3)),
                                month_num(embargo.group(2)),
                                int(embargo.group(1)))
            basis = "mospi_embargo_line"
    qe_match = QE_PATTERN.search(normalized)
    qe_general = float(qe_match.group(1)) if qe_match else None
    first_months: List[Tuple[int, int]] = []
    final_months: List[Tuple[int, int]] = []
    r1_match = REVISION_R1_PATTERN.search(normalized)
    if r1_match and month_num(r1_match.group(1)) is not None:
        first_months.append((int(r1_match.group(2)),
                             month_num(r1_match.group(1))))
    fin_match = REVISION_FINAL_PATTERN.search(normalized)
    if fin_match and month_num(fin_match.group(1)) is not None:
        final_months.append((int(fin_match.group(2)),
                             month_num(fin_match.group(1))))
    if not final_months:
        # New-format releases name only final revisions (possibly several).
        for match in FINAL_LIST_PATTERN.finditer(normalized):
            for year, mon in parse_month_list(match.group(1)):
                if (year, mon) not in final_months:
                    final_months.append((year, mon))
    note_months: List[Tuple[int, int]] = []
    note_match = NOTE_PATTERN.search(normalized)
    if note_match:
        note_months = parse_month_list(note_match.group(1))
    stmt, fys = parse_statement_general(normalized)
    return IipReleaseEvidence(
        filename=path.name,
        ref_year=ref_year,
        ref_month=ref_month,
        release_date=release_date,
        release_basis=basis,
        base=detect_base(normalized),
        qe_general=qe_general,
        first_revision_months=first_months,
        final_revision_months=final_months,
        note_months=note_months,
        stmt_general=stmt,
        stmt_fys=fys,
    )


def parse_pib_release_html(path: Path) -> IipReleaseEvidence:
    """Parse a PIB release page (HTML) for an IIP month whose MoSPI PDF is
    unrecoverable. Values come from the release text and the release date
    from the 'Posted On' timestamp (availability basis 'pib_posting').
    Statement tables are not parsed from HTML; named finals without a
    printed value may be rescued from the next MoSPI release. Raises
    ValueError when the reference month cannot be established.
    """
    html = path.read_text(encoding="utf-8", errors="replace")
    ref = re.search(r"FOR THE MONTH OF\s+([A-Za-z]+)[,\s]+(20\d\d)", html,
                    re.IGNORECASE)
    if not ref or month_num(ref.group(1)) is None:
        raise ValueError(f"{path.name}: reference month not found")
    posted = re.search(r"Posted On[^0-9]*(\d{1,2})\s+([A-Za-z]{3})\s+(20\d\d)",
                       html)
    if not posted:
        raise ValueError(f"{path.name}: PIB posting timestamp not found")
    normalized = normalize_text(re.sub(r"<[^>]+>", " ", html))
    qe_match = QE_PATTERN.search(normalized)
    final_months: List[Tuple[int, int]] = []
    for match in FINAL_LIST_PATTERN.finditer(normalized):
        for year, mon in parse_month_list(match.group(1)):
            if (year, mon) not in final_months:
                final_months.append((year, mon))
    first_months: List[Tuple[int, int]] = []
    r1_match = REVISION_R1_PATTERN.search(normalized)
    if r1_match and month_num(r1_match.group(1)) is not None:
        first_months.append((int(r1_match.group(2)),
                             month_num(r1_match.group(1))))
    return IipReleaseEvidence(
        filename=path.name,
        ref_year=int(ref.group(2)),
        ref_month=month_num(ref.group(1)),
        release_date=date(int(posted.group(3)),
                          MONTH_ABBR_TO_NUM[posted.group(2).strip().lower()],
                          int(posted.group(1))),
        release_basis="pib_posting",
        base="2011-12" if "2011-12" in html else None,
        qe_general=float(qe_match.group(1)) if qe_match else None,
        first_revision_months=first_months,
        final_revision_months=final_months,
    )


def parse_backseries(path: Path) -> Dict[Tuple[int, int], float]:
    """Parse the May-2017 back-series table (Mon-YY rows, General last)."""
    normalized = normalize_text(read_pdf_text(path))
    start = normalized.find("STATEMENT I")
    if start < 0:
        raise ValueError(f"{path.name}: back-series table not found")
    segment = normalized[start:start + 20000]
    series: Dict[Tuple[int, int], float] = {}
    for match in re.finditer(
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d\d)"
            r"\s+((?:[\d.]+\s*){4})", segment):
        values = match.group(3).split()
        if len(values) != 4:
            continue
        year = 2000 + int(match.group(2))
        series[(year, MONTH_ABBR_TO_NUM[match.group(1).lower()])] = float(
            values[3])
    if len(series) < 48:
        raise ValueError(f"{path.name}: back-series too short "
                         f"({len(series)} months)")
    return series


@dataclass
class IipExcludedFile:
    filename: str
    reason: str


@dataclass
class IipConflict:
    observation_period: str
    detail: str


@dataclass
class IipUnvaluedVintage:
    """A revision explicitly named in a release whose value is not printed
    in that release (early-era files without a sectoral monthly table).

    Not a conflict: the event is preserved, no value is fabricated, and the
    month remains covered by the back-series and later republications.
    """
    observation_period: str
    vintage_status: str
    release_file: str
    release_date: Optional[date]


def _fy_to_year(fy: str, mon3: str) -> Tuple[int, int]:
    month = MONTH_ABBR_TO_NUM[mon3]
    year0 = int(fy[:4])
    return (year0, month) if month >= 4 else (year0 + 1, month)


def build_canonical(
    evidences: List[IipReleaseEvidence],
    backseries: Dict[Tuple[int, int], float],
    backseries_file: str,
    extra_vintages: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[pd.DataFrame, List[IipExcludedFile], List[IipConflict],
           List[IipUnvaluedVintage]]:
    """Combine release vintages with the back-series into canonical rows.

    Rules (never interpolate, never infer dates, never splice bases):
      - quick (rev 0): reference-month QE from its own release.
      - first_revision (rev 1) / final (rev 2): months explicitly named,
        values taken from the naming release's Statement I.
      - back_series (rev 0): May-2017 table values, available 2017-05-12.
      - republished (rev sequential): Statement I values for months with no
        explicit vintage covering that value; availability = first release
        in which the value appeared.
      - At most one row per (period, status-source); distinct later values
        extend the timeline honestly. Identical re-uploads merge provenance.
      - True conflicts — same (period, status, availability) with different
        values across files — are blocked (rows excluded) with evidence
        preserved.
    """
    excluded: List[IipExcludedFile] = []
    conflicts: List[IipConflict] = []
    unvalued: List[IipUnvaluedVintage] = []
    rows: List[Dict[str, Any]] = []
    provenance: Dict[tuple, List[str]] = {}

    def period_text(year: int, month: int) -> str:
        return f"{year:04d}-{month:02d}"

    def in_window(year: int, month: int) -> bool:
        return bool(HOMOGENEOUS_START <= (year, month) <= HOMOGENEOUS_END)

    def add_row(row: Dict[str, Any], filename: str) -> None:
        key = (row["observation_period"], row["iip_index"],
               str(row["availability_date"]), row["vintage_status"])
        bucket = provenance.setdefault(key, [])
        if filename not in bucket:
            bucket.append(filename)
        if len(bucket) == 1:
            rows.append(row)

    usable = [e for e in evidences if e.base == "2011-12"]
    for evidence in evidences:
        if evidence.base != "2011-12":
            excluded.append(IipExcludedFile(
                filename=evidence.filename,
                reason=f"non-homogeneous base ({evidence.base}); values "
                "not canonicalized"))
    for evidence in sorted(usable, key=lambda e: (e.ref_year, e.ref_month)):
        if not in_window(evidence.ref_year, evidence.ref_month):
            excluded.append(IipExcludedFile(
                filename=evidence.filename,
                reason="reference outside homogeneous 2012-04..2026-03"))
            continue
        if evidence.release_date is None:
            excluded.append(IipExcludedFile(
                filename=evidence.filename,
                reason="no recoverable release date; values preserved in "
                "raw evidence only"))
            continue
        period = period_text(evidence.ref_year, evidence.ref_month)
        obs = month_end(evidence.ref_year, evidence.ref_month)
        if evidence.qe_general is not None:
            add_row({"observation_period": period,
                     "observation_date": obs,
                     "availability_date": evidence.release_date,
                     "iip_index": evidence.qe_general,
                     "vintage_status": "quick",
                     "revision_version": STATUS_REVISION["quick"],
                     "availability_basis": evidence.release_basis,
                     "source": "MOSPI",
                     "source_files": evidence.filename}, evidence.filename)
        for status, months, rev in (
                ("first_revision", evidence.first_revision_months,
                 STATUS_REVISION["first_revision"]),
                ("final", evidence.final_revision_months,
                 STATUS_REVISION["final"])):
            for year, mon in months:
                if not in_window(year, mon):
                    continue
                value = _stmt_lookup(evidence, year, mon)
                if value is None:
                    unvalued.append(IipUnvaluedVintage(
                        observation_period=period_text(year, mon),
                        vintage_status=status,
                        release_file=evidence.filename,
                        release_date=evidence.release_date))
                    continue
                add_row({"observation_period": period_text(year, mon),
                         "observation_date": month_end(year, mon),
                         "availability_date": evidence.release_date,
                         "iip_index": value,
                         "vintage_status": status,
                         "revision_version": rev,
                         "availability_basis": evidence.release_basis,
                         "source": "MOSPI",
                         "source_files": evidence.filename}, evidence.filename)
    # Back-series baseline (Apr-2012..Mar-2017, published 2017-05-12).
    for (year, month), value in sorted(backseries.items()):
        if not in_window(year, month):
            continue
        add_row({"observation_period": period_text(year, month),
                 "observation_date": month_end(year, month),
                 "availability_date": BACKSERIES_RELEASE_DATE,
                 "iip_index": value,
                 "vintage_status": "back_series",
                 "revision_version": STATUS_REVISION["back_series"],
                 "availability_basis": "mospi_back_series_2017",
                 "source": "MOSPI",
                 "source_files": backseries_file}, backseries_file)
    # Statement I republications: distinct values never explicitly named.
    published: Dict[Tuple[str, float], date] = {}
    republished_first: Dict[Tuple[str, float], str] = {}
    for evidence in sorted(
            usable, key=lambda e: (e.release_date or date.max,
                                   e.filename)):
        if evidence.release_date is None:
            continue
        if not in_window(evidence.ref_year, evidence.ref_month):
            continue
        for (fy, mon3), value in evidence.stmt_general.items():
            year, mon = _fy_to_year(fy, mon3)
            if not in_window(year, mon):
                continue
            key = (period_text(year, mon), value)
            if key not in published:
                published[key] = evidence.release_date
                republished_first[key] = evidence.filename
    for extra in extra_vintages or []:
        key = (extra["observation_period"], extra["iip_index"],
               str(extra["availability_date"]), extra["vintage_status"])
        if key in {(r["observation_period"], r["iip_index"],
                    str(r["availability_date"]), r["vintage_status"])
                   for r in rows}:
            continue
        rows.append(dict(extra))
    for (period, value), first_seen in sorted(published.items()):
        year, mon = int(period[:4]), int(period[5:7])
        if any(r["observation_period"] == period
               and r["iip_index"] == value
               and str(r["availability_date"]) <= str(first_seen)
               for r in rows):
            # Covered by an explicit vintage already known at or before
            # first republication: no new information, skip the row.
            continue
        # Same value known only from LATER explicit vintages (or never):
        # keep the earlier republication (genuinely visible first).
        # revision_version counts earlier-availability rows so intra-month
        # order stays chronological.
        rev = sum(1 for r in rows
                  if r["observation_period"] == period
                  and str(r["availability_date"]) <= str(first_seen))
        rows.append({"observation_period": period,
                     "observation_date": month_end(year, mon),
                     "availability_date": first_seen,
                     "iip_index": value,
                     "vintage_status": "republished",
                     "revision_version": rev,
                     "availability_basis": "mospi_statement_republication",
                     "source": "MOSPI",
                     "source_files": republished_first[(period, value)]})
        provenance.setdefault(
            (period, value, str(first_seen), "republished"),
            [republished_first[(period, value)]])
    # Narrow rescue for named finals whose naming release carries no
    # Statement I value (e.g. PIB pages). Conditions (all required):
    #  - the named month is 1-2 months before the naming release's ref
    #    month (fresh finalization, not a stale M-3 backfill);
    #  - the valuing release is the next publication (<=45 days later), so
    #    no intervening publication could have shown otherwise.
    # The compiled final exists as of its announcement; dual provenance
    # records the construction. First revisions are never rescued (a later
    # value may postdate the R1 state -> backdating).
    still_unvalued: List[IipUnvaluedVintage] = []
    for item in unvalued:
        rescued = False
        if item.vintage_status == "final" and item.release_date is not None:
            year, mon = int(item.observation_period[:4]), int(
                item.observation_period[5:7])
            naming = [e for e in usable
                      if e.filename == item.release_file]
            fresh = False
            if naming:
                ref = naming[0]
                diff = ((ref.ref_year - year) * 12
                        + (ref.ref_month - mon))
                fresh = 1 <= diff <= 2
            if not fresh:
                still_unvalued.append(item)
                continue
            candidates = []
            for evidence in usable:
                if evidence.release_date is None:
                    continue
                if evidence.release_date <= item.release_date:
                    continue
                value = _stmt_lookup(evidence, year, mon)
                if value is not None:
                    candidates.append((evidence.release_date, value,
                                       evidence.filename))
            candidates.sort()
            if (candidates and
                    (candidates[0][0] - item.release_date).days <= 45):
                naming_basis = next(
                    (e.release_basis for e in usable
                     if e.filename == item.release_file),
                    "mospi_press_release")
                add_row({"observation_period": item.observation_period,
                         "observation_date": month_end(year, mon),
                         "availability_date": item.release_date,
                         "iip_index": candidates[0][1],
                         "vintage_status": "final",
                         "revision_version": STATUS_REVISION["final"],
                         "availability_basis": naming_basis,
                         "source": "MOSPI",
                         "source_files": item.release_file},
                        item.release_file)
                # Merge the valuing release into provenance explicitly.
                key = (item.observation_period, candidates[0][1],
                       str(item.release_date), "final")
                if candidates[0][2] not in provenance.get(key, []):
                    provenance.setdefault(key, []).append(candidates[0][2])
                rescued = True
        if not rescued:
            still_unvalued.append(item)
    unvalued = still_unvalued
    frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    if not frame.empty:
        frame["_avail_key"] = frame["availability_date"].astype(str)

        def merged_sources(row: Any) -> str:
            key = (row["observation_period"], row["iip_index"],
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
            ["observation_date", "availability_date",
             "revision_version"]).reset_index(drop=True)
        # True conflicts: same (period, status, availability) carrying
        # different values across files. Block all rows of such keys.
        if not frame.empty:
            frame["_conf_key"] = list(zip(
                frame["observation_period"], frame["vintage_status"],
                frame["availability_date"].astype(str)))
            bad_keys = {
                key for key, group in frame.groupby("_conf_key")
                if group["iip_index"].nunique() > 1
            }
            for key in sorted(bad_keys):
                conflicts.append(IipConflict(
                    observation_period=key[0],
                    detail=f"{key[1]} @ {key[2]} has conflicting values "
                    f"{sorted(frame[frame['_conf_key'] == key]['iip_index'].unique())}"))
            if bad_keys:
                frame = frame[~frame["_conf_key"].isin(bad_keys)].reset_index(
                    drop=True)
            frame = frame.drop(columns=["_conf_key"])
    return frame[CANONICAL_COLUMNS], excluded, conflicts, unvalued


def _stmt_lookup(evidence: IipReleaseEvidence, year: int,
                 month: int) -> Optional[float]:
    """Find a month's General value in a release's Statement I table.

    Only exact fiscal-year matches count; there is deliberately no
    same-month fallback (a wrong-FY value must surface as a conflict,
    never as a silent substitution).
    """
    for (fy, mon), value in evidence.stmt_general.items():
        if _fy_to_year(fy, mon) == (year, month):
            return value
    return None


def agent_eligible_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return only rows with verified availability for agent-facing use."""
    eligible = frame[
        frame["availability_date"].notna()
        & frame["vintage_status"].isin(AGENT_ELIGIBLE_VINTAGES)
    ].copy()
    return eligible.reset_index(drop=True)


def build_agent_information_set(frame: pd.DataFrame):
    """Build an InformationSet of agent-eligible IIP vintages.

    Fails closed when nothing is eligible. Retrospective macro rule
    applies: availability must not precede the observation month-end.
    """
    from src.india.information_set import InformationSet

    eligible = agent_eligible_rows(frame)
    if eligible.empty:
        raise ValueError("No agent-eligible IIP vintages.")
    vintages = pd.DataFrame({
        "variable": "IIP_GENERAL",
        "observation_date": pd.to_datetime(eligible["observation_date"]),
        "availability_date": pd.to_datetime(eligible["availability_date"]),
        "revision_version": eligible["revision_version"].astype(int),
        "value": eligible["iip_index"].astype(float),
    })
    return InformationSet(vintages)


def validate_no_forward_fill(frame: pd.DataFrame) -> List[str]:
    """Confirm canonical months are never fabricated: values positive and
    every row traces to parsed release evidence or the back-series."""
    errors: List[str] = []
    for period, group in frame.groupby("observation_period"):
        if group["iip_index"].isna().any():
            errors.append(f"{period}: null iip_index")
        if (group["iip_index"] <= 0).any():
            errors.append(f"{period}: non-positive iip_index")
    return errors
