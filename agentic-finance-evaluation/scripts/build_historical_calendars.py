#!/usr/bin/env python3
"""Build the canonical historical venue-isolated calendar from raw evidence.

Deterministic: same raw files -> byte-identical canonical CSV.
Reads official NSE circulars (PDF) + 2026 NSE JSON + hardcoded DERIVED
specials table (secondary citations, never VERIFIED). Writes:

    data/processed/india/calendars/historical_calendar.csv
    data/processed/india/calendars/historical_calendar_metadata.json

MCX/RBI/MOSPI/EIA daily rows: only what official evidence supports
(MCX Muhurat DERIVED x2; RBI/MOSPI/EIA header-only -> fully UNKNOWN by
absence). Run from project root:

    python scripts/build_historical_calendars.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.india.historical_calendar import HistoricalCalendar, HistoricalCalendarRecord

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "data" / "raw" / "india" / "calendars"
OUT_DIR = BASE / "data" / "processed" / "india" / "calendars"

# Fixed acquisition date for retrieved_at (rebuild-stable provenance).
RETRIEVED_AT = "2026-09-13T12:30:00+00:00"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

# (filename, source_url, coverage_note)
ARTIFACTS: list[tuple[str, str, str]] = [
    ("CMTR39612.pdf", "https://archives.nseindia.com/content/circulars/CMTR39612.pdf",
     "NSE CM holidays 2019"),
    ("CMTR42877.pdf", "https://archives.nseindia.com/content/circulars/CMTR42877.pdf",
     "NSE CM holidays 2020"),
    ("CMTR46623.pdf", "https://archives.nseindia.com/content/circulars/CMTR46623.pdf",
     "NSE CM holidays 2021"),
    ("CMTR50050.pdf", "https://archives.nseindia.com/content/circulars/CMTR50050.pdf",
     "NSE Muhurat timings 2021-11-04"),
    ("CMTR50560.pdf", "https://archives.nseindia.com/content/circulars/CMTR50560.pdf",
     "NSE CM holidays 2022"),
    ("CMTR54757.pdf", "https://archives.nseindia.com/content/circulars/CMTR54757.pdf",
     "NSE CM holidays 2023"),
    ("COM54758.pdf", "https://archives.nseindia.com/content/circulars/COM54758.pdf",
     "NSE commodity-derivatives holidays 2023 (reference only)"),
    ("CMTR61518.pdf", "https://nsearchives.nseindia.com/content/circulars/CMTR61518.pdf",
     "NSE CM ad-hoc holiday 2024-05-20 elections"),
    ("CMTR65587.pdf", "https://archives.nseindia.com/content/circulars/CMTR65587.pdf",
     "NSE CM holidays 2025"),
    ("CMTR70319.pdf", "https://nsearchives.nseindia.com/content/circulars/CMTR70319.pdf",
     "NSE Muhurat timings 2025-10-21"),
    ("FAOP71777.pdf", "https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf",
     "NSE F&O holidays 2026 (CM dates corroborated by 2026 JSON)"),
    ("FAOP72352.pdf", "https://nsearchives.nseindia.com/content/circulars/FAOP72352.pdf",
     "NSE live Budget session 2026-02-01"),
    ("CMPT61957.pdf", "https://nsearchives.nseindia.com/content/circulars/CMPT61957.pdf",
     "NCL clearing timings special session 2024-05-18"),
    ("FBIL_REFERENCE_RATE_FINAL.pdf",
     "https://www.fbil.org.in/uploads/FBIL_REFERENCE_RATE_FINAL_fa318d5727.pdf",
     "FBIL reference-rate methodology (schedule rule, no day map)"),
    ("NEW_timeline_IIP_press_release_17.04.25.pdf",
     "https://www.mospi.gov.in/sites/default/files/press_release/NEW_timeline_IIP_press_release_17.04.25.pdf",
     "MoSPI IIP 28th-day schedule from Apr-2025 (schedule rule)"),
]

NSE_JSON = BASE / "data" / "raw" / "india" / "indices" / "nse_trading_holidays_2026.json"
NSE_JSON_URL = "https://www.nseindia.com/api/holiday-master?type=trading"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

MUHURAT_RE = re.compile(
    r"Muhurat Trading will be conducted on\s+"
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
    r"([A-Za-z]+\s+\d{1,2},?\s*\d{4})",
    re.IGNORECASE,
)


def parse_nse_holiday_pdf(text: str) -> tuple[list[tuple[date, str]], list[tuple[date, str]], str | None]:
    """Return (weekday_holidays, weekend_entries, muhurat_date_iso_or_None).

    weekday_holidays: [(date, description)] from the main table (CLOSED).
    weekend_entries: [(date, description)] from the Sat/Sun table; entries
      carrying the Muhurat footnote are separated as the special session.
    """
    # Scope parsing to the holiday tables: drop the circular header (which
    # contains the circular's own issue date) by starting at the first
    # "Sr. No. ... Date ... Description" table header.
    header = re.search(r"Sr\.\s*No\.\s*Date\s*Day\s*Description", text,
                       re.IGNORECASE)
    body = text if header is None else text[header.start():]
    lower = body.lower()
    marker = "holidays falling on saturday"
    idx = lower.find(marker)
    main_text = body if idx < 0 else body[:idx]
    weekend_text = "" if idx < 0 else body[idx:]
    # Muhurat footnote date: "Muhurat Trading will be conducted on <date>".
    muhurat_match = MUHURAT_RE.search(body)
    muhurat_iso: str | None = None
    if muhurat_match:
        muhurat_iso = _parse_date_str(muhurat_match.group(1)).isoformat()
    # Extract dated rows with trailing description text (up to newline).
    main_rows = _dated_rows(main_text)
    # The Muhurat footnote sentence itself contains a date; remove it from
    # the weekend section so the footnote date is not double-counted as a
    # weekend-table row (weekday Muhurats live in the main table).
    weekend_scan = MUHURAT_RE.sub("", weekend_text)
    weekend_rows = _dated_rows(weekend_scan)
    return (main_rows, weekend_rows, muhurat_iso)


def _parse_date_str(s: str) -> date:
    m = DATE_RE.search(s)
    assert m, f"unparseable date: {s!r}"
    return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))


def _dated_rows(text: str) -> list[tuple[date, str]]:
    rows: list[tuple[date, str]] = []
    for m in DATE_RE.finditer(text):
        day = date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        # description: rest of line after the date match.
        line_end = text.find("\n", m.end())
        desc = text[m.end():line_end if line_end > 0 else m.end() + 80].strip()
        desc = re.sub(r"\s+", " ", desc)
        # strip leading day-of-week token.
        desc = re.sub(
            r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+",
            "", desc, flags=re.IGNORECASE,
        )
        rows.append((day, desc[:120]))
    # dedup preserving order
    seen: set[date] = set()
    out: list[tuple[date, str]] = []
    for d, desc in rows:
        if d not in seen:
            seen.add(d)
            out.append((d, desc))
    return out


# DERIVED specials / closures without in-repo primary circulars.
# Each entry: (date, session_type, market_status, special, holiday_reason,
#              notes, evidence_status). Never VERIFIED.
DERIVED_NSE: list[tuple[str, str, str, bool, str, str, str]] = [
    ("2020-02-01", "special_weekend", "SPECIAL", True, "Union Budget Saturday",
     "Full normal-hours Budget session per broker/exchange notices (LiveMint/Zerodha 31-Jan-2020); primary NSE circular not yet acquired.",
     "DERIVED"),
    ("2024-01-20", "special_weekend", "SPECIAL", True, "DR live session",
     "NSE/BSE DR live session Sat per exchange notices (Business Standard 19-Jan-2024; CNBC-TV18); one report says full normal hours after 22-Jan holiday declared; intraday segmentation unresolved; primary DR circular not yet acquired.",
     "DERIVED"),
    ("2024-03-02", "special_weekend", "SPECIAL", True, "DR live session",
     "Prior DR Saturday referenced in May-2024 session coverage (ET/India Today); primary circular not yet acquired.",
     "DERIVED"),
    ("2024-01-22", "holiday", "CLOSED", False, "Ram Mandir consecration / NI Act holiday",
     "NSE modification of circular 59917 per RBI press 2023-2024/1716 and Maharashtra NI-Act holiday (LiveMint/CNBC-TV18 Jan-2024); modification circular PDF not yet acquired.",
     "DERIVED"),
    ("2024-11-01", "special_session", "SPECIAL", True, "Diwali Muhurat",
     "Muhurat Friday per BSE 2024 holiday notice; NSE 2024 annual circular not yet acquired.",
     "DERIVED"),
]

# MCX Muhurat DERIVED rows (secondary: broker holiday tables + gold obs consistency).
DERIVED_MCX: list[tuple[str, str]] = [
    ("2019-10-27", "Muhurat evening session per commodity holiday tables (TrueData 2019); MCX circular not yet acquired."),
    ("2020-11-14", "Muhurat evening session per commodity holiday tables (TrueData 2020); MCX circular not yet acquired."),
]


def build() -> tuple[HistoricalCalendar, dict]:
    cal = HistoricalCalendar()
    provenance: dict = {"artifacts": [], "exclusions": [], "conflicts": [],
                        "unknown_ranges": []}
    digests: dict[str, str] = {}
    for filename, url, coverage in ARTIFACTS:
        path = RAW / filename
        if not path.exists():
            provenance["exclusions"].append(f"Missing raw artifact: {filename}")
            continue
        digest = sha256(path)
        digests[filename] = digest
        provenance["artifacts"].append({
            "path": f"data/raw/india/calendars/{filename}",
            "sha256": digest,
            "byte_size": path.stat().st_size,
            "source_url": url,
            "retrieved_at": RETRIEVED_AT,
            "coverage": coverage,
        })

    def add(record: HistoricalCalendarRecord) -> None:
        before = len(cal.conflicts)
        cal.add(record)
        if len(cal.conflicts) > before:
            first, second = cal.conflicts[-1]
            provenance["conflicts"].append(
                f"{first.venue} {first.calendar_date}: "
                f"{first.session_type} vs {second.session_type}")

    # --- NSE annual holiday PDFs (VERIFIED CLOSED + weekend info) ---
    annual_files = ["CMTR39612.pdf", "CMTR42877.pdf", "CMTR46623.pdf",
                    "CMTR50560.pdf", "CMTR54757.pdf", "CMTR65587.pdf"]
    for filename in annual_files:
        path = RAW / filename
        if not path.exists():
            continue
        mains, weekends, muhurat_iso = parse_nse_holiday_pdf(pdf_text(path))
        for day, desc in mains:
            # Skip the Muhurat-day entry itself when it appears in the main
            # table (e.g. weekday Diwali-Laxmi Pujan IS the Muhurat venue):
            # it is a holiday for the normal session but hosts the evening
            # special session; encode as SPECIAL to preserve tradeability.
            if muhurat_iso and day.isoformat() == muhurat_iso:
                add(HistoricalCalendarRecord(
                    venue="NSE_CM", calendar_date=day, session_type="special_session",
                    market_status="SPECIAL", segment="CM", asset_class="equity",
                    special_session=True, holiday_reason=f"Diwali Muhurat ({desc})",
                    session_notes="Annual circular Muhurat footnote; intraday timings by separate circular.",
                    source="NSE", source_url=_url(filename), source_file=filename,
                    retrieved_at=RETRIEVED_AT, raw_sha256=digests[filename],
                    evidence_status="VERIFIED"))
            else:
                add(HistoricalCalendarRecord(
                    venue="NSE_CM", calendar_date=day, session_type="holiday",
                    market_status="CLOSED", segment="CM", asset_class="equity",
                    special_session=False, holiday_reason=desc,
                    session_notes="Annual NSE CM trading-holiday circular, main table.",
                    source="NSE", source_url=_url(filename), source_file=filename,
                    retrieved_at=RETRIEVED_AT, raw_sha256=digests[filename],
                    evidence_status="VERIFIED"))
        for day, desc in weekends:
            if muhurat_iso and day.isoformat() == muhurat_iso:
                timing = ""
                if filename == "CMTR50050.pdf":
                    timing = ""
                add(HistoricalCalendarRecord(
                    venue="NSE_CM", calendar_date=day, session_type="special_weekend",
                    market_status="SPECIAL", segment="CM", asset_class="equity",
                    special_session=True, holiday_reason=f"Diwali Muhurat ({desc})",
                    session_notes="Annual circular weekend table + Muhurat footnote; timings by separate circular (e.g. CMTR50050 for 2021: 18:15-19:15).",
                    source="NSE", source_url=_url(filename), source_file=filename,
                    retrieved_at=RETRIEVED_AT, raw_sha256=digests[filename],
                    evidence_status="VERIFIED"))
            # Non-Muhurat weekend entries are informational only (weekend is
            # not automatically closed by our model); no row is written so
            # they resolve UNKNOWN rather than fabricated CLOSED.

    # --- 2026 NSE JSON (VERIFIED; CM segment only for trading status) ---
    if NSE_JSON.exists():
        payload = json.loads(NSE_JSON.read_text(encoding="utf-8"))
        cm_rows = payload.get("CM", [])
        jdigest = sha256(NSE_JSON)
        provenance["artifacts"].append({
            "path": "data/raw/india/indices/nse_trading_holidays_2026.json",
            "sha256": jdigest,
            "byte_size": NSE_JSON.stat().st_size,
            "source_url": NSE_JSON_URL,
            "retrieved_at": "2026-09-10T15:05:39+00:00",
            "coverage": "NSE trading holidays 2026 (all segments)",
        })
        for rec in cm_rows:
            try:
                day = datetime.strptime(rec["tradingDate"], "%d-%b-%Y").date()
            except Exception:
                continue
            desc = str(rec.get("description", ""))
            if "Diwali" in desc and "Laxmi" in desc:
                add(HistoricalCalendarRecord(
                    venue="NSE_CM", calendar_date=day, session_type="special_weekend",
                    market_status="SPECIAL", segment="CM", asset_class="equity",
                    special_session=True, holiday_reason=f"Diwali Muhurat ({desc})",
                    session_notes="2026 holiday-master + Market Timings page Muhurat note; timings by later circular.",
                    source="NSE", source_url=NSE_JSON_URL,
                    source_file="nse_trading_holidays_2026.json",
                    retrieved_at="2026-09-10T15:05:39+00:00", raw_sha256=jdigest,
                    evidence_status="VERIFIED"))
            else:
                # Weekday entries -> CLOSED. Weekend non-Muhurat entries ->
                # informational only, no row (UNKNOWN by absence).
                if day.weekday() < 5:
                    add(HistoricalCalendarRecord(
                        venue="NSE_CM", calendar_date=day, session_type="holiday",
                        market_status="CLOSED", segment="CM", asset_class="equity",
                        special_session=False, holiday_reason=desc,
                        session_notes="2026 NSE holiday-master CM segment.",
                        source="NSE", source_url=NSE_JSON_URL,
                        source_file="nse_trading_holidays_2026.json",
                        retrieved_at="2026-09-10T15:05:39+00:00", raw_sha256=jdigest,
                        evidence_status="VERIFIED"))

    # --- Ad-hoc VERIFIED closures/sessions from in-repo primary circulars ---
    if (RAW / "CMTR61518.pdf").exists():  # 2024-05-20 election holiday
        add(HistoricalCalendarRecord(
            venue="NSE_CM", calendar_date=date(2024, 5, 20), session_type="holiday",
            market_status="CLOSED", segment="CM", asset_class="equity",
            special_session=False, holiday_reason="Parliamentary Elections Mumbai",
            session_notes="NSE/CMTR/61518 08-Apr-2024 modifies 2023 circular 59722.",
            source="NSE",
            source_url="https://nsearchives.nseindia.com/content/circulars/CMTR61518.pdf",
            source_file="CMTR61518.pdf", retrieved_at=RETRIEVED_AT,
            raw_sha256=digests["CMTR61518.pdf"], evidence_status="VERIFIED"))
    if (RAW / "CMPT61957.pdf").exists():  # 2024-05-18 special session
        add(HistoricalCalendarRecord(
            venue="NSE_CM", calendar_date=date(2024, 5, 18), session_type="special_weekend",
            market_status="SPECIAL", segment="CM", asset_class="equity",
            special_session=True, holiday_reason="DR live trading session",
            session_notes="NCL/CMPT/61957 clearing timings for 18-May-2024 special live session (PR 09:15-10:00, DR session 2); further ref NCL/CMPT/61924 07-May-2024.",
            source="NSE",
            source_url="https://nsearchives.nseindia.com/content/circulars/CMPT61957.pdf",
            source_file="CMPT61957.pdf", retrieved_at=RETRIEVED_AT,
            raw_sha256=digests["CMPT61957.pdf"], evidence_status="VERIFIED"))
    if (RAW / "FAOP72352.pdf").exists():  # 2026-02-01 Budget Sunday
        add(HistoricalCalendarRecord(
            venue="NSE_CM", calendar_date=date(2026, 2, 1), session_type="special_weekend",
            market_status="SPECIAL", segment="CM", asset_class="equity",
            special_session=True, holiday_reason="Union Budget live session",
            session_notes="NSE/FAOP/72352 16-Jan-2026: standard hours 09:15-15:30.",
            source="NSE",
            source_url="https://nsearchives.nseindia.com/content/circulars/FAOP72352.pdf",
            source_file="FAOP72352.pdf", retrieved_at=RETRIEVED_AT,
            raw_sha256=digests["FAOP72352.pdf"], evidence_status="VERIFIED"))

    # --- Ad-hoc DERIVED closures (secondary evidence; never VERIFIED) ---
    for iso, reason, notes in [
        ("2019-04-29", "General Elections Mumbai",
         "Weekday closure per exchange holiday notices mirrored by broker tables (TrueData 2019); modification circular not yet acquired."),
        ("2019-10-21", "Maharashtra Assembly Elections",
         "Weekday closure per exchange holiday notices mirrored by broker tables (TrueData 2019); modification circular not yet acquired."),
    ]:
        add(HistoricalCalendarRecord(
            venue="NSE_CM", calendar_date=date.fromisoformat(iso),
            session_type="holiday", market_status="CLOSED", segment="CM",
            asset_class="equity", special_session=False,
            holiday_reason=reason, session_notes=notes, source="NSE/secondary",
            source_url="", source_file="", retrieved_at=RETRIEVED_AT,
            raw_sha256="", evidence_status="DERIVED"))

    # --- Regular/weekly-closure DERIVED rows for fully covered years ---
    # (moved after all event rows; see below)
    for iso, stype, mstatus, special, reason, notes, estate in DERIVED_NSE:
        add(HistoricalCalendarRecord(
            venue="NSE_CM", calendar_date=date.fromisoformat(iso),
            session_type=stype, market_status=mstatus, segment="CM",
            asset_class="equity", special_session=special,
            holiday_reason=reason, session_notes=notes, source="NSE/secondary",
            source_url="", source_file="", retrieved_at=RETRIEVED_AT,
            raw_sha256="", evidence_status=estate))

    # --- MCX DERIVED Muhurat rows ---
    for iso, notes in DERIVED_MCX:
        add(HistoricalCalendarRecord(
            venue="MCX", calendar_date=date.fromisoformat(iso),
            session_type="special_weekend", market_status="SPECIAL",
            segment="COM", asset_class="commodity", special_session=True,
            holiday_reason="Diwali Muhurat evening session",
            session_notes=notes, source="MCX/secondary",
            source_url="", source_file="", retrieved_at=RETRIEVED_AT,
            raw_sha256="", evidence_status="DERIVED",
            availability_note="Morning/evening split not resolved at date grain; evening participation only."))

    provenance["unknown_ranges"] = [
        "NSE_CM 1996-01-01..2018-12-31: no official holiday circulars acquired (UNKNOWN by absence).",
        "NSE_CM 2024-01-01..2024-12-31: base annual circular not acquired; only ad-hoc DERIVED/VERIFIED rows present.",
        "MCX all years: no official MCX holiday circular acquired (2026 page blocked); only 2 DERIVED Muhurat rows.",
        "RBI_FX: Mumbai bank-holiday day map not acquired; no daily rows (fully UNKNOWN).",
        "MOSPI/EIA: no market calendar by design (fully UNKNOWN as market venues).",
    ]
    # --- Regular/weekly-closure DERIVED rows for fully covered years ---
    # A year is fully covered only when its annual holiday circular is
    # in-repo. For such years, Mon-Fri dates absent from the exhaustive
    # holiday list are regular OPEN sessions, and weekends without a
    # special session are CLOSED (NSE weekly Mon-Fri schedule per the
    # market-timings page). Both are DERIVED (by exclusion), never
    # VERIFIED, and never extend to uncovered years. Runs last so event
    # rows (VERIFIED holidays/specials, DERIVED ad-hoc) always win.
    COVERED_YEARS = (2019, 2020, 2021, 2022, 2023, 2025, 2026)
    for year in COVERED_YEARS:
        day = date(year, 1, 1)
        while day.year == year:
            if cal.get("NSE_CM", day) is None:
                if day.weekday() < 5:
                    add(HistoricalCalendarRecord(
                        venue="NSE_CM", calendar_date=day, session_type="regular",
                        market_status="OPEN", segment="CM", asset_class="equity",
                        special_session=False, holiday_reason="",
                        session_notes="DERIVED by exclusion: weekday absent from exhaustive annual holiday list (NSE weekly Mon-Fri schedule).",
                        source="NSE", source_url="", source_file="",
                        retrieved_at=RETRIEVED_AT, raw_sha256="",
                        evidence_status="DERIVED"))
                else:
                    add(HistoricalCalendarRecord(
                        venue="NSE_CM", calendar_date=day, session_type="closed",
                        market_status="CLOSED", segment="CM", asset_class="equity",
                        special_session=False, holiday_reason="Weekend (no special session)",
                        session_notes="DERIVED: weekend without special session in covered year (NSE weekly schedule).",
                        source="NSE", source_url="", source_file="",
                        retrieved_at=RETRIEVED_AT, raw_sha256="",
                        evidence_status="DERIVED"))
            day = day.fromordinal(day.toordinal() + 1)
    return cal, provenance


def _url(filename: str) -> str:
    for name, url, _ in ARTIFACTS:
        if name == filename:
            return url
    return ""


def main() -> None:
    cal, provenance = build()
    errors = cal.validate()
    if errors:
        print("Calendar validation errors:")
        for e in errors:
            print(" ", e)
        sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / "historical_calendar.csv"
    _, digest = cal.to_csv(out_csv)
    nse_cov = cal.coverage("NSE_CM")
    mcx_cov = cal.coverage("MCX")
    provenance.update({
        "canonical_path": "data/processed/india/calendars/historical_calendar.csv",
        "canonical_sha256": digest,
        "canonical_rows": len(cal.to_rows()),
        "nse_cm_coverage": [str(x) if x else None for x in nse_cov],
        "mcx_coverage": [str(x) if x else None for x in mcx_cov],
        "processing": "scripts/build_historical_calendars.py: regex-parse annual NSE CM PDFs (main table CLOSED VERIFIED; Muhurat weekend SPECIAL VERIFIED), 2026 JSON CM segment, ad-hoc primary circulars, DERIVED specials table; no weekday inference; no observation-derived rows.",
    })
    meta_path = OUT_DIR / "historical_calendar_metadata.json"
    meta_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    print(f"rows={len(cal.to_rows())} sha={digest}")
    print(f"NSE_CM coverage={nse_cov} MCX coverage={mcx_cov}")


if __name__ == "__main__":
    main()
