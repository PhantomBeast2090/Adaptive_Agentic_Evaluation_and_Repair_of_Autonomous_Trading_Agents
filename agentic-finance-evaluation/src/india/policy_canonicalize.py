"""RBI policy-rate event canonicalization (dual-source reconciliation).

Validates two official RBI evidence families in place (raw files are
never rewritten) and builds an event-based canonical dataset under
``data/processed/india/macro/``:

1. BACKBONE — RBI Handbook of Statistics on the Indian Economy,
   Table "Major Monetary Policy Rates and Reserve Requirements"
   (Table 40 in the 2025-26 edition, Table 43 in 2024-25, Table 44 in
   2022-23 — table numbering shifts by edition, so provenance cites
   edition + page id). Provides EFFECTIVE dates + rate levels for
   Bank Rate and LAF Repo / Reverse Repo / SDF / MSF. CRR and SLR
   columns are present in the table but EXCLUDED from this dataset
   (reserve requirements, not corridor policy rates).

2. ANNOUNCEMENT SIDE — official RBI MPC resolutions, Governor
   statements, MSF circulars, MPRs, meeting minutes (MPC era,
   Oct-2016 onwards) and RBI Annual Report chronology annexes,
   appendix tables and monetary-policy chapters (Governor-statement
   era, pre-Oct-2016). Provides ANNOUNCEMENT dates, decisions,
   corridor rates and stance.

Reconciliation rules (never violated):
- announcement_date and effective_date are separate fields; neither is
  inferred from the other. Events without announcement evidence keep
  announcement_date null with a conservative availability fallback.
- One MPC decision may change several rates at once: canonical rows
  are per (announcement, effective, rate_type) but share a decision_id
  identifying the underlying policy decision.
- change_bps is computed from the Table predecessor and cross-checked
  against announced changes where stated; mismatches block the event.
- Conflicting records block canonicalization instead of being resolved
  arbitrarily. The output stays EVENT-BASED: no daily conversion, no
  forward-fill, no interpolation.

Canonical schema follows ``RBIPolicyRecord`` (plus provenance):
    announcement_date, effective_date, observation_date, availability_date,
    availability_basis, rate_type, rate_pct, previous_rate_pct, change_bps,
    change_basis, stance, stance_source, source, source_url, source_files,
    announcement_source, decision_id, reconciliation_status
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

BACKBONE_FILENAME = "rbi_handbook_2025-26_table40_policy_rates.xlsx"
BACKBONE_EDITION = "Handbook of Statistics on the Indian Economy, 2025-26 (Table 40; Table 43 in 2024-25)"
BACKBONE_PAGE_ID = "PublicationsView.aspx?id=23865"
EVIDENCE_DIRNAME = "policy"

# Table column index -> canonical rate_type (CRR/SLR columns excluded).
RATE_COLUMNS: Dict[str, int] = {
    "BANK_RATE": 2,
    "REPO": 3,
    "REVERSE_REPO": 4,
    "SDF": 5,
    "MSF": 6,
}

CANONICAL_COLUMNS = [
    "announcement_date",
    "effective_date",
    "observation_date",
    "availability_date",
    "availability_basis",
    "rate_type",
    "rate_pct",
    "previous_rate_pct",
    "change_bps",
    "change_basis",
    "stance",
    "stance_source",
    "source",
    "source_url",
    "source_files",
    "announcement_source",
    "decision_id",
    "reconciliation_status",
]

STANCE_TERMS = [
    "withdrawal of accommodation",
    "accommodative",
    "neutral",
    "calibrated tightening",
]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_policy_raw_files(raw_dir: Path) -> List[Path]:
    """Return Table backbone + announcement evidence files, sorted."""
    backbone = sorted((raw_dir).glob("rbi_handbook_*_table*_policy_rates.xlsx"))
    evidence = sorted((raw_dir / EVIDENCE_DIRNAME).glob("rbi_*"))
    return backbone + evidence


def parse_table_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


@dataclass
class BackboneEvent:
    effective_date: date
    rate_type: str
    rate_pct: float
    sheet: str


@dataclass
class ExcludedBackboneRow:
    source_file: str
    date_text: str
    reason: str


def parse_backbone_table(path: Path) -> Tuple[List[BackboneEvent], List[ExcludedBackboneRow]]:
    """Parse Table 40 sheets into rate_type-level change events.

    A cell containing a number is a rate level set on that effective
    date; '-' / empty means no change for that rate_type on that date.
    """
    import openpyxl
    import warnings

    warnings.filterwarnings("ignore")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    events: List[BackboneEvent] = []
    excluded: List[ExcludedBackboneRow] = []
    for sheet in workbook.sheetnames:
        for row in workbook[sheet].iter_rows(values_only=True):
            if row is None or len(row) < 9:
                continue
            eff = parse_table_date(row[1])
            if eff is None:
                continue
            for rate_type, col in RATE_COLUMNS.items():
                value = row[col] if col < len(row) else None
                if value is None or (isinstance(value, str) and value.strip() in ("", "-")):
                    continue
                try:
                    level = float(value)
                except (TypeError, ValueError):
                    excluded.append(
                        ExcludedBackboneRow(
                            source_file=f"{path.name}#{sheet}",
                            date_text=eff.isoformat(),
                            reason=f"non-numeric {rate_type} cell: {value!r}",
                        )
                    )
                    continue
                events.append(
                    BackboneEvent(
                        effective_date=eff, rate_type=rate_type,
                        rate_pct=level, sheet=sheet,
                    )
                )
    events.sort(key=lambda e: (e.effective_date, e.rate_type))
    return events, excluded


class _TableParser(HTMLParser):
    """Extract HTML tables as row lists (standard library only)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_td = False
        self.cell: List[str] = []
        self.row: List[str] = []
        self.rows: List[List[str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in ("td", "th"):
            self.in_td = True
            self.cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self.in_td:
            self.in_td = False
            self.row.append(" ".join("".join(self.cell).split()))
        elif tag == "tr":
            if any(c.strip() for c in self.row):
                self.rows.append(self.row)
            self.row = []

    def handle_data(self, data: str) -> None:
        if self.in_td:
            self.cell.append(data)


def html_text(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text)


def parse_full_date(text: str) -> Optional[date]:
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def month_number(name: str) -> Optional[int]:
    cleaned = name.strip().rstrip(".")
    for fmt in ("%B", "%b"):
        try:
            return datetime.strptime(cleaned, fmt).month
        except ValueError:
            continue
    return None


@dataclass
class AnnouncementItem:
    announcement_date: date
    initiative: str
    source_file: str
    evidence_kind: str  # appendix_table | chronology | resolution | minutes | statement | circular | mpr | chapter


def extract_appendix_announcements(
    path: Path, kinds: str = "appendix_table"
) -> List[AnnouncementItem]:
    """Extract 'Date of Announcement | Policy Initiative' table rows.

    Skips bare rate-level tables ('Effective since' style where the second
    cell is just a number): those document effective levels, not
    announcements, and crediting them as announcement dates would collapse
    the announcement/effective distinction this dataset must preserve.
    """
    parser = _TableParser()
    parser.feed(path.read_bytes().decode("utf-8", errors="replace"))
    items: List[AnnouncementItem] = []
    for row in parser.rows:
        if len(row) < 2:
            continue
        announced = parse_full_date(row[0])
        if announced is None:
            continue
        if re.fullmatch(r"[\d.]+(\s*\(.*\))?", row[1].strip()):
            continue
        items.append(
            AnnouncementItem(
                announcement_date=announced, initiative=row[1][:2000],
                source_file=path.name, evidence_kind=kinds,
            )
        )
    return items


def extract_chronology_announcements(path: Path) -> List[AnnouncementItem]:
    """Extract grid (year/month/day) and flat chronology entries."""
    parser = _TableParser()
    parser.feed(path.read_bytes().decode("utf-8", errors="replace"))
    items: List[AnnouncementItem] = []
    current_year: Optional[int] = None
    current_month: Optional[int] = None
    last_flat_year: Optional[int] = None
    in_monetary_section = True
    for row in parser.rows:
        cells = [c.strip() for c in row]
        if not cells:
            continue
        # Flat style: full date in first cell.
        announced = parse_full_date(cells[0]) if len(cells) >= 2 else None
        if announced is not None and len(cells) >= 2:
            last_flat_year = announced.year
            items.append(
                AnnouncementItem(
                    announcement_date=announced, initiative=cells[1][:2000],
                    source_file=path.name, evidence_kind="chronology",
                )
            )
            continue
        # Year-less "Month D" rows inherit the year of the most recent
        # flat full-date row (annex tables list entries in rough
        # chronological order within a July-to-June coverage window).
        if len(cells) >= 2 and last_flat_year is not None:
            month_day = re.match(
                r"(January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+(\d{1,2})$",
                cells[0].strip(),
            )
            if month_day:
                try:
                    announced = date(
                        last_flat_year,
                        month_number(month_day.group(1)),  # type: ignore[arg-type]
                        int(month_day.group(2)),
                    )
                    items.append(
                        AnnouncementItem(
                            announcement_date=announced,
                            initiative=cells[1][:2000],
                            source_file=path.name,
                            evidence_kind="chronology",
                        )
                    )
                    continue
                except (ValueError, TypeError):
                    pass
        # Grid style: year / month / day inheritance; section headers
        # re-assert the year and switch section scope. Only Section I
        # (monetary policy measures) entries are announcement evidence.
        if len(cells) < 3:
            continue
        first, second = cells[0], cells[1]
        text = cells[-1]
        if re.fullmatch(r"(19|20)\d{2}", first):
            current_year = int(first)
            if "MONETARY POLICY" in text.upper():
                in_monetary_section = True
            elif re.match(r"^(II|III|IV|V)\.", text):
                in_monetary_section = False
            continue
        if not in_monetary_section:
            continue
        month = month_number(first) if first else None
        if month is not None:
            current_month = month
            if not re.fullmatch(r"\d{1,2}", second):
                continue
            day = int(second)
        elif first == "" and re.fullmatch(r"\d{1,2}", second):
            if current_month is None:
                continue
            day = int(second)
        else:
            continue
        if current_year is None or current_month is None:
            continue
        try:
            announced = date(current_year, current_month, day)
        except ValueError:
            continue
        items.append(
            AnnouncementItem(
                announcement_date=announced, initiative=text[:2000],
                source_file=path.name, evidence_kind="chronology",
            )
        )
    return items


_CHAPTER_RATE_RE = re.compile(
    r"((?:On\s+)?(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},?\s+20\d{2})"
    r"[^.]{0,400}?(repo rate|reverse repo|MSF|Bank Rate|SDF|policy rate|stance)",
    re.I,
)


def extract_chapter_narratives(path: Path) -> List[AnnouncementItem]:
    """Extract dated policy-rate sentences from monetary-policy chapters.

    Weakest announcement evidence tier: narrative sentences carry dates
    but are retrospective summaries, so they corroborate rather than
    establish announcement timing.
    """
    text = html_text(path)
    sentences = re.split(r"\.\s+", text)
    items: List[AnnouncementItem] = []
    for sentence in sentences:
        match = _CHAPTER_RATE_RE.search(sentence)
        if not match:
            continue
        announced = parse_full_date(
            re.sub(r"^On\s+", "", match.group(1), flags=re.I)
        )
        if announced is None:
            continue
        items.append(
            AnnouncementItem(
                announcement_date=announced,
                initiative=sentence[:2000],
                source_file=path.name,
                evidence_kind="monetary_chapter_narrative",
            )
        )
    return items


def collect_announcements(policy_dir: Path) -> List[AnnouncementItem]:
    """Collect announcement items from every evidence HTML file.

    Runs appendix-table, chronology and narrative extractors as appropriate
    per file role. The same announcement found in several files is kept
    once per file for provenance; reconciliation matches on dates.
    """
    items: List[AnnouncementItem] = []
    seen: set = set()
    for path in sorted(policy_dir.glob("*.html")):
        name = path.name
        candidates: List[AnnouncementItem] = []
        if "chronology" in name:
            # Annex files carry both grid chronologies and appendix tables.
            candidates = (
                extract_chronology_announcements(path)
                + extract_appendix_announcements(path)
                + extract_chapter_narratives(path)
            )
        else:
            candidates = (
                extract_appendix_announcements(path)
                + extract_chapter_narratives(path)
                + extract_dated_decisions(path)
            )
        for item in candidates:
            key = (item.announcement_date, item.initiative, item.source_file)
            if key not in seen:
                seen.add(key)
                items.append(item)
    return items


def _clean_level(cell: str) -> Optional[Tuple[float, Optional[int]]]:
    """Parse '7.25 (+0.25)' style cells into (level, change_bps)."""
    text = cell.strip()
    if not text or text == "-":
        return None
    level_match = re.match(r"(\d+\.\d+|\d+)", text)
    if not level_match:
        return None
    change_match = re.search(r"\(\s*([+-]?\d*\.?\d+)\s*\)", text)
    change = None
    if change_match:
        try:
            change = _round_bps(float(change_match.group(1)))
        except ValueError:
            change = None
    return float(level_match.group(1)), change


@dataclass
class ChapterRateRow:
    effective_date: date
    rate_type: str
    rate_pct: float
    change_bps: Optional[int]
    source_file: str


def extract_chapter_rate_tables(path: Path) -> List[ChapterRateRow]:
    """Extract typed 'Movements in Key Policy Rates' tables from chapters.

    Maps columns to canonical rate types (Reverse/Repo/MSF/Bank; CRR/SLR
    skipped). Used to cross-validate the Table 40 backbone, never as a
    competing primary source.
    """
    parser = _TableParser()
    parser.feed(path.read_bytes().decode("utf-8", errors="replace"))
    rows = parser.rows
    found: List[ChapterRateRow] = []
    for index, row in enumerate(rows):
        cells = [c.strip() for c in row]
        joined = " | ".join(cells)
        if "Movements in Key Policy" not in joined and "Effective since" not in joined:
            continue
        # Header row identifies column positions.
        header = cells
        col_map: Dict[int, str] = {}
        for pos, cell in enumerate(header):
            lowered = cell.lower()
            if "reverse repo" in lowered:
                col_map[pos] = "REVERSE_REPO"
            elif "repo rate" in lowered or lowered == "repo":
                col_map[pos] = "REPO"
            elif "marginal standing" in lowered or lowered == "msf":
                col_map[pos] = "MSF"
            elif "bank rate" in lowered:
                col_map[pos] = "BANK_RATE"
            elif "standing deposit" in lowered or lowered == "sdf":
                col_map[pos] = "SDF"
        if not col_map:
            continue
        for data in rows[index + 1:]:
            if len(data) < 2:
                continue
            eff = parse_full_date(data[0]) or parse_table_date(data[0])
            if eff is None:
                # End of this table when a non-date row with text appears
                # after at least one data row... simply skip non-dates.
                if any(len(c) > 40 for c in data):
                    break
                continue
            for pos, rate_type in col_map.items():
                if pos >= len(data):
                    continue
                parsed = _clean_level(data[pos])
                if parsed is None:
                    continue
                level, change = parsed
                found.append(
                    ChapterRateRow(
                        effective_date=eff, rate_type=rate_type,
                        rate_pct=level, change_bps=change,
                        source_file=path.name,
                    )
                )
    return found


_DECISION_RE = re.compile(
    r"(repo rate|reverse repo|MSF|Bank Rate|SDF|LAF)[^.]{0,250}?"
    r"(reduced|increased|cut|raised|hiked|adjusted)[^.]{0,250}?"
    r"(\d+\.\d+)\s*per cent",
    re.I,
)
_DATE_RE = re.compile(
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+20\d{2})"
)


def extract_dated_decisions(path: Path) -> List[AnnouncementItem]:
    """Extract dated rate-decision sentences (e.g. monthly review digests).

    Finds decision sentences stating a rate change and attributes the
    nearest preceding full date in the surrounding text as the
    announcement date. Used for RBI publication pages that summarize
    decisions without a uniform table layout.
    """
    text = html_text(path)
    sentences = re.split(r"(?<=[.])\s+", text)
    items: List[AnnouncementItem] = []
    window = ""
    for sentence in sentences:
        window = (window + " " + sentence)[-600:]
        if not _DECISION_RE.search(sentence):
            continue
        dates = _DATE_RE.findall(window)
        if not dates:
            continue
        announced = parse_full_date(dates[-1])
        if announced is None:
            continue
        # Corridor-rate levels (reverse repo/MSF/Bank Rate) are typically
        # stated in sentences adjacent to the repo decision sentence, so
        # the surrounding window is preserved for level matching.
        context_start = max(0, len(window) - 600)
        items.append(
            AnnouncementItem(
                announcement_date=announced,
                initiative=(window[context_start:] + " ||| " + sentence)[:2000],
                source_file=path.name,
                evidence_kind="dated_decision_narrative",
            )
        )
    return items


@dataclass
class ResolutionEvidence:
    source_file: str
    page_date: Optional[date]
    meeting_start: Optional[date]
    meeting_end: Optional[date]
    announcement_date: Optional[date]
    announcement_basis: str
    levels: Dict[str, float] = field(default_factory=dict)
    change_bps_stated: Optional[int] = None
    stance: Optional[str] = None
    effective_words: Optional[str] = None


_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)


def _find_dates(text: str) -> List[Tuple[str, int, int]]:
    """Find (matched_text, start, end) for common RBI date spellings."""
    patterns = [
        r"(?:Date\s*:\s*)([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})",
        r"(?:Date\s*:\s*)(\d{2}/\d{2}/\d{4})",
        r"([A-Z][a-z]+\s+\d{1,2}(?:\s*(?:and|to)\s*\d{1,2})?,\s+\d{4})",
    ]
    found = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            found.append((match.group(1), match.start(), match.end()))
    return found


def _parse_loose_date(text: str) -> Optional[date]:
    text = text.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _extract_levels(text: str) -> Dict[str, float]:
    """Extract announced target rate levels per rate family.

    RBI decision sentences state changes as 'from X per cent to Y per
    cent'; the TARGET (post-decision) level is the meaningful one, so the
    'to Y' value is preferred and the first bare number is only a fallback.
    """
    levels: Dict[str, float] = {}
    families = {
        # REVERSE_REPO first: its sentences contain the substring
        # "repo rate", so the REPO head uses a negative lookbehind.
        "REVERSE_REPO": r"reverse repo rate",
        "REPO": r"(?<!reverse )repo rate",
        "MSF": r"(?:MSF|marginal standing facility)[^r]*?rate",
        "BANK_RATE": r"Bank [Rr]ate",
        "SDF": r"(?:SDF|standing deposit facility)[^r]*?rate",
    }
    for rate_type, head in families.items():
        for match in re.finditer(head, text, re.I):
            # Sentence-scoped window: decimal points inside numbers must
            # not truncate the window (so cut at period+space, not '.').
            tail = text[match.start():match.start() + 400]
            cut = re.search(r"\.\s+[A-Z0-9\"']", tail)
            sentence = tail[: cut.start() + 1] if cut else tail
            target = re.search(r"\bto\s+(\d+\.\d+)\s*per cent", sentence, re.I)
            if target is None:
                target = re.search(r"(\d+\.\d+)\s*per cent", sentence)
            if target is None:
                continue
            try:
                levels[rate_type] = float(target.group(1))
            except ValueError:
                continue
            break
    return levels


def _extract_change_bps(text: str) -> Optional[int]:
    match = re.search(
        r"(?:reduce|increase|cut|raise|hike)[^.\n]{0,80}?policy repo rate[^.\n]{0,80}?by\s+(\d+)\s*basis points",
        text, re.I,
    )
    if match:
        return int(match.group(1))
    return None


def _extract_stance(text: str) -> Optional[str]:
    for term in STANCE_TERMS:
        if re.search(
            r"stance[^.]{0,120}?" + re.escape(term)
            + r"|" + re.escape(term) + r"[^.]{0,80}?stance",
            text, re.I,
        ):
            return term
    return None


def extract_resolution_evidence(path: Path) -> ResolutionEvidence:
    """Extract announcement/decision/stance from a resolution-class page.

    Page types are detected from content, never assumed from filenames:
    - resolution/governor/circular pages carry their announcement date in
      a 'Date :' header or dated title/letter text;
    - minutes pages carry the meeting dates in text while their header
      date is the (later) minutes release date.
    """
    text = html_text(path)
    is_minutes = "Minutes of the Monetary Policy Committee" in text
    page_dates = [
        _parse_loose_date(found[0]) for found in _find_dates(text) if _parse_loose_date(found[0])
    ]
    header_date = page_dates[0] if page_dates else None
    meeting_match = re.search(
        r"(?:meeting (?:today )?\(?|meetings?(?: scheduled)? (?:during|from|on) |held (?:on|during|from) )"
        r"([A-Z][a-z]+ \d{1,2}(?:\s*(?:,|and|to|-|–)\s*\d{1,2})?,? \d{4})",
        text,
    )
    meeting_end: Optional[date] = None
    if meeting_match:
        span = meeting_match.group(1)
        year_match = re.search(r"(\d{4})\s*$", span)
        year = year_match.group(1) if year_match else None
        days = re.findall(r"\b(\d{1,2})\b", span)
        month_match = re.search(r"([A-Z][a-z]+)", span)
        if month_match and days and year:
            try:
                meeting_end = datetime.strptime(
                    f"{month_match.group(1)} {days[-1]} {year}", "%B %d %Y"
                ).date()
            except ValueError:
                try:
                    meeting_end = datetime.strptime(
                        f"{month_match.group(1)} {days[-1]} {year}", "%b %d %Y"
                    ).date()
                except ValueError:
                    meeting_end = None
    if is_minutes:
        announcement = meeting_end
        basis = "meeting_end_date_from_minutes_text"
    else:
        # The page header/title/letter date is the announcement date.
        # Meeting dates in text are recorded as context only: an unrelated
        # referenced meeting must never override the page's own date.
        announcement = header_date
        basis = "page_date_header"
    return ResolutionEvidence(
        source_file=path.name,
        page_date=header_date,
        meeting_start=None,
        meeting_end=meeting_end,
        announcement_date=announcement,
        announcement_basis=basis,
        levels=_extract_levels(text),
        change_bps_stated=_extract_change_bps(text),
        stance=_extract_stance(text),
        effective_words=(
            "with immediate effect" if "with immediate effect" in text else None
        ),
    )


def extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF evidence file (pypdf). Raw bytes untouched."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = [(page.extract_text() or "") for page in reader.pages]
    return re.sub(r"\s+", " ", "\n".join(parts))


def extract_pdf_evidence(path: Path) -> ResolutionEvidence:
    """Extract announcement/decision/stance from a PDF evidence file."""
    text = extract_pdf_text(path)
    is_minutes = "Minutes of the Monetary Policy Committee" in text
    found = _find_dates(text)
    header_date = _parse_loose_date(found[0][0]) if found else None
    meeting_match = re.search(
        r"(?:meeting (?:today )?\(?|meetings?(?: scheduled)? (?:during|from|on) |held (?:on|during|from) )"
        r"([A-Z][a-z]+ \d{1,2}(?:\s*(?:,|and|to|-|–)\s*\d{1,2})?,? \d{4})",
        text,
    )
    meeting_end: Optional[date] = None
    if meeting_match:
        span = meeting_match.group(1)
        year_match = re.search(r"(\d{4})\s*$", span)
        year = year_match.group(1) if year_match else None
        days = re.findall(r"\b(\d{1,2})\b", span)
        month_match = re.search(r"([A-Z][a-z]+)", span)
        if month_match and days and year:
            for fmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    meeting_end = datetime.strptime(
                        f"{month_match.group(1)} {days[-1]} {year}", fmt
                    ).date()
                    break
                except ValueError:
                    continue
    dated_title = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),\s+(20\d{2})",
        text[:800],
    )
    title_date = None
    if dated_title:
        title_date = parse_full_date(
            f"{dated_title.group(1)} {dated_title.group(2)}, {dated_title.group(3)}"
        )
    if is_minutes:
        announcement, basis = meeting_end, "meeting_end_date_from_minutes_text"
    elif title_date is not None:
        announcement, basis = title_date, "dated_title"
    else:
        announcement, basis = header_date, "page_date_header"
    return ResolutionEvidence(
        source_file=path.name,
        page_date=header_date,
        meeting_start=None,
        meeting_end=meeting_end,
        announcement_date=announcement,
        announcement_basis=basis,
        levels=_extract_levels(text),
        change_bps_stated=_extract_change_bps(text),
        stance=_extract_stance(text),
        effective_words=(
            "with immediate effect" if "with immediate effect" in text else None
        ),
    )


def parse_full_date(text: str) -> Optional[date]:
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def collect_chapter_rates(policy_dir: Path) -> List[ChapterRateRow]:
    """Collect typed rate-table rows from monetary chapters."""
    rows: List[ChapterRateRow] = []
    for path in sorted(policy_dir.glob("rbi_ar_*monetary_ch*.html")):
        rows.extend(extract_chapter_rate_tables(path))
    return rows


def cross_validate_backbone(
    backbone: List[BackboneEvent], chapter_rows: List[ChapterRateRow]
) -> Tuple[int, List[Dict[str, Any]]]:
    """Cross-check Table levels against chapter rate tables.

    Returns (matching_count, mismatches). Any mismatch is a conflict
    record blocking that event's validation.
    """
    back = {
        (e.effective_date, e.rate_type): e.rate_pct for e in backbone
    }
    matching = 0
    mismatches: List[Dict[str, Any]] = []
    for row in chapter_rows:
        key = (row.effective_date, row.rate_type)
        if key not in back:
            continue
        if abs(back[key] - row.rate_pct) > 1e-9:
            mismatches.append(
                {
                    "effective_date": row.effective_date.isoformat(),
                    "rate_type": row.rate_type,
                    "table_level": back[key],
                    "chapter_level": row.rate_pct,
                    "source_file": row.source_file,
                    "reason": "chapter rate table disagrees with Table 40",
                }
            )
        else:
            matching += 1
    return matching, mismatches


_RESOLUTION_KEYWORDS = (
    "mpc_resolution", "mpc_statement", "mpc_minutes", "gov_statement",
    "msf_circular", "mpr_", "sdf_statement", "35087", "fqr_",
    "annual_policy_", "tqrap",
)


def collect_resolutions(policy_dir: Path) -> List[ResolutionEvidence]:
    """Extract resolution-class evidence from statement/minutes pages."""
    items: List[ResolutionEvidence] = []
    for path in sorted(policy_dir.glob("*.html")):
        if any(k in path.name for k in _RESOLUTION_KEYWORDS):
            items.append(extract_resolution_evidence(path))
    return items


def collect_pdf_evidence(policy_dir: Path) -> List[ResolutionEvidence]:
    """Extract evidence from saved PDF statements/minutes."""
    return [
        extract_pdf_evidence(path)
        for path in sorted(policy_dir.glob("*.pdf"))
    ]


@dataclass
class CanonicalEvent:
    announcement_date: Optional[date]
    effective_date: date
    observation_date: date
    availability_date: date
    availability_basis: str
    rate_type: str
    rate_pct: float
    previous_rate_pct: Optional[float]
    change_bps: Optional[int]
    change_basis: str
    stance: Optional[str]
    stance_source: Optional[str]
    source: str
    source_url: str
    source_files: str
    announcement_source: Optional[str]
    decision_id: str
    reconciliation_status: str
    notes: str = ""


def _round_bps(value: float) -> int:
    return int(round(value * 100))


def _item_supports_event(
    initiative: str, rate_pct: float, computed_bps: Optional[int]
) -> bool:
    """Check a chronology/appendix text mentions this event's level/change.

    Prevents attributing an event to an unrelated dated entry (e.g. a
    settlements-system note days before a rate decision).
    """
    text = initiative.lower()
    level_forms = {str(rate_pct), f"{rate_pct:.2f}", f"{rate_pct:.1f}"}
    if any(form in text for form in level_forms):
        return True
    if computed_bps is not None:
        magnitude = abs(computed_bps)
        if re.search(
            rf"\b{magnitude}\s*(?:basis points|bps)\b", text
        ) and "repo" in text:
            return True
    return False


def reconcile_events(
    backbone: List[BackboneEvent],
    announcements: List[AnnouncementItem],
    resolutions: List[ResolutionEvidence],
    backbone_name: str,
) -> Tuple[List[CanonicalEvent], List[Dict[str, Any]]]:
    """Reconcile Table rate events with announcement evidence.

    Returns (canonical events, blocked/conflict records). Rules:
    - predecessor per rate_type from Table order gives previous_rate_pct
      and computed change_bps;
    - an announcement matches when its date equals the effective date
      ('with immediate effect' pattern) or falls within the 10 days
      before it AND mentions a consistent rate/level/change;
    - matched events share decision_id per announcement date; unmatched
      events keep announcement_date null, availability falls back to the
      effective date (flagged), and status announcement_unverified;
    - announced change text disagreeing with the Table change blocks.
    """
    by_rate: Dict[str, List[BackboneEvent]] = {}
    for event in backbone:
        by_rate.setdefault(event.rate_type, []).append(event)

    previous: Dict[str, Optional[float]] = {rate: None for rate in by_rate}
    canonical: List[CanonicalEvent] = []
    blocked: List[Dict[str, Any]] = []

    for rate_type in sorted(by_rate):
        for event in sorted(by_rate[rate_type], key=lambda e: e.effective_date):
            prev = previous[rate_type]
            computed_bps = (
                _round_bps(event.rate_pct - prev) if prev is not None else None
            )
            candidates: List[Tuple[date, str, str, Optional[int], Optional[str], Dict[str, float]]] = []
            for item in announcements:
                delta = (event.effective_date - item.announcement_date).days
                if -1 <= delta <= 10 and _item_supports_event(
                    item.initiative, event.rate_pct, computed_bps
                ):
                    candidates.append(
                        (item.announcement_date, item.source_file, "annual_report_or_chronology",
                         None, None, {})
                    )
            for resolution in resolutions:
                if resolution.announcement_date is None:
                    continue
                delta = (event.effective_date - resolution.announcement_date).days
                if not (-1 <= delta <= 10):
                    continue
                level = resolution.levels.get(rate_type)
                if level is not None and abs(level - event.rate_pct) > 1e-9:
                    continue
                candidates.append(
                    (resolution.announcement_date, resolution.source_file, "mpc_resolution_or_statement",
                     resolution.change_bps_stated, resolution.stance, resolution.levels)
                )
            # Prefer resolution-class evidence, then dated RBI chronology /
            # appendix tables, then retrospective chapter narratives. Within
            # a tier the latest announcement at or before effectiveness wins:
            # announcements precede effectiveness, so the closest prior dated
            # record is the correct attribution (never an unrelated earlier
            # entry in the window).
            def _tier(kind: str) -> int:
                if kind == "mpc_resolution_or_statement":
                    return 0
                if kind == "monetary_chapter_narrative":
                    return 2
                return 1

            candidates.sort(key=lambda c: (_tier(c[2]), -c[0].toordinal()))
            best_tier = _tier(candidates[0][2]) if candidates else None
            status = "announcement_unverified"
            announcement: Optional[date] = None
            announcement_source: Optional[str] = None
            stance: Optional[str] = None
            stance_source: Optional[str] = None
            change_basis = "table_computed"
            if candidates:
                chosen = candidates[0]
                announcement = chosen[0]
                same_day = [
                    c for c in candidates
                    if c[0] == announcement and c[2] == "mpc_resolution_or_statement"
                ]
                stances = {c[4] for c in same_day if c[4]} | {
                    c[4] for c in candidates if c[0] == announcement and c[4]
                }
                if len(stances) == 1:
                    stance = next(iter(stances))
                    stance_source = ";".join(
                        sorted({c[1] for c in candidates if c[0] == announcement and c[4] == stance})
                    )
                announced_changes = {
                    c[3] for c in candidates
                    if c[0] == announcement and c[3] is not None
                }
                # Announced-change text in RBI resolutions refers to the
                # policy repo rate; it cross-checks REPO events only.
                # Corridor rates are validated via stated levels instead.
                if (
                    rate_type == "REPO"
                    and announced_changes
                    and computed_bps is not None
                    and all(abs(change) != abs(computed_bps) for change in announced_changes)
                    and abs(computed_bps) not in {c for c in announced_changes}
                ):
                    blocked.append(
                        {
                            "effective_date": event.effective_date.isoformat(),
                            "rate_type": rate_type,
                            "reason": "announced change disagrees with Table change",
                        }
                    )
                    status = "change_conflict"
                else:
                    status = "verified" if chosen[2] == "mpc_resolution_or_statement" else "announcement_cross_checked"
                    if announced_changes and rate_type == "REPO":
                        change_basis = "announcement_cross_checked"
                announcement_source = ";".join(
                    sorted({c[1] for c in candidates if c[0] == announcement})
                )
            if announcement is not None:
                availability, availability_basis = announcement, "announcement_date"
                decision_id = f"D{announcement.isoformat()}"
            else:
                availability, availability_basis = (
                    event.effective_date,
                    "effective_date_fallback_announcement_unverified",
                )
                decision_id = f"U{event.effective_date.isoformat()}"
            provenance = {backbone_name}
            if announcement_source:
                provenance.update(announcement_source.split(";"))
            canonical.append(
                CanonicalEvent(
                    announcement_date=announcement,
                    effective_date=event.effective_date,
                    observation_date=event.effective_date,
                    availability_date=availability,
                    availability_basis=availability_basis,
                    rate_type=rate_type,
                    rate_pct=event.rate_pct,
                    previous_rate_pct=prev,
                    change_bps=computed_bps,
                    change_basis=change_basis,
                    stance=stance,
                    stance_source=stance_source,
                    source="RBI",
                    source_url="https://www.rbi.org.in/",
                    source_files=";".join(sorted(provenance)),
                    announcement_source=announcement_source,
                    decision_id=decision_id,
                    reconciliation_status=status,
                    notes="",
                )
            )
            previous[rate_type] = event.rate_pct
    return canonical, blocked


def build_canonical_frame(events: List[CanonicalEvent]) -> pd.DataFrame:
    """Render canonical events deterministically (no daily conversion)."""
    frame = pd.DataFrame([
        {
            "announcement_date": (
                "" if e.announcement_date is None else e.announcement_date.isoformat()
            ),
            "effective_date": e.effective_date.isoformat(),
            "observation_date": e.observation_date.isoformat(),
            "availability_date": e.availability_date.isoformat(),
            "availability_basis": e.availability_basis,
            "rate_type": e.rate_type,
            "rate_pct": e.rate_pct,
            "previous_rate_pct": (
                "" if e.previous_rate_pct is None else e.previous_rate_pct
            ),
            "change_bps": "" if e.change_bps is None else e.change_bps,
            "change_basis": e.change_basis,
            "stance": "" if e.stance is None else e.stance,
            "stance_source": "" if e.stance_source is None else e.stance_source,
            "source": e.source,
            "source_url": e.source_url,
            "source_files": e.source_files,
            "announcement_source": (
                "" if e.announcement_source is None else e.announcement_source
            ),
            "decision_id": e.decision_id,
            "reconciliation_status": e.reconciliation_status,
            "notes": e.notes,
        }
        for e in events
    ])
    frame = frame.sort_values(
        ["effective_date", "rate_type"]
    ).reset_index(drop=True)
    return frame[CANONICAL_COLUMNS]
