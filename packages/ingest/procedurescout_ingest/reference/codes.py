"""Reference codes: HCPCS Level II and MS-DRG titles into ref.code.

HCPCS Level II — CMS quarterly "Alpha-Numeric HCPCS File" (zip). We read the
fixed-width text member (320-character records; layout per the CMS HCPCS
record layout):
    1-5 code, 6-10 sequence, 11 record id (3 = procedure first line,
    4 = continuation, 7 = modifier first line, 8 = modifier continuation),
    12-91 long description, 92-119 short description, 269-276 added date,
    277-284 action effective date, 285-292 termination date (YYYYMMDD),
    293 action code.
Only Level II codes (a letter A-V and four digits) are stored. Five-digit
numeric codes would be CPT (AMA text, D-002) and are never stored; modifiers
are skipped. If more than 1% of procedure records fail layout checks the
whole load is refused (the layout probably changed).

MS-DRG — CMS IPPS final rule Table 5 (zip of .xlsx and/or .txt). The header
row is found by its "MS-DRG" and "...TITLE..." cells; only code + title are
stored (weights are not prices and are not loaded).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, text

from procedurescout_core.enums import CodeSystem

from .common import LoadStats, SourceError, decode_text, zip_members

RECORD_LENGTH = 320
LEVEL2_CODE = re.compile(r"^[A-V][0-9]{4}$")
CPT_LIKE = re.compile(r"^[0-9]{4}[0-9A-Z]$")
MAX_LAYOUT_FAILURE_PERMILLE = 10


@dataclass
class CodeRow:
    code: str
    long: str
    short: str | None
    added: date | None
    terminated: date | None


def _yyyymmdd(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    if not re.fullmatch(r"[0-9]{8}", raw):
        raise ValueError(raw)
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def join_segments(segments: list[str]) -> str:
    """Join the 80-character description segments of one code. CMS wraps long
    descriptions across records; a space goes between segments unless the
    previous segment fills all 80 columns and the next starts without a blank
    (the break then fell inside a word)."""
    out = ""
    prev_full = False
    for raw in segments:
        seg = raw.rstrip()
        if not seg.strip():
            prev_full = False
            continue
        if out and (not prev_full or seg.startswith(" ")):
            out += " "
        out += seg.strip()
        prev_full = len(seg) >= 80
    return " ".join(out.split())


def looks_like_hcpcs_text(name: str, data: bytes) -> bool:
    if not name.lower().endswith(".txt"):
        return False
    """Fixed-width HCPCS records: a code (or blank-padded modifier) in columns
    1-5 and a record id in column 11. Trailing blanks may be trimmed (the
    October 2026 file is), so line length is not required; parse_hcpcs pads."""
    lines = [ln for ln in decode_text(data).splitlines()[:300] if ln.strip()]
    good = sum(
        1
        for ln in lines
        if ln[10:11] in {"3", "4", "7", "8"}
        and (LEVEL2_CODE.match(ln[0:5]) or CPT_LIKE.match(ln[0:5]) or ln[0:3] == "   ")
    )
    return len(lines) > 0 and good * 10 >= len(lines) * 9


def describe_text_members(data: bytes) -> dict[str, object]:
    """Line count, length range and the first two lines of each .txt member,
    for error messages when no member looks like the HCPCS records file."""
    out: dict[str, object] = {}
    if not data.startswith(b"PK\x03\x04"):
        return out
    for name, member in zip_members(data).items():
        if not name.lower().endswith(".txt"):
            continue
        lines = decode_text(member).splitlines()
        lengths = [len(ln) for ln in lines[:300]]
        out[name] = {
            "lines": len(lines),
            "length_range_first_300": [min(lengths, default=0), max(lengths, default=0)],
            "first_lines": [ln[:120] for ln in lines[:2]],
        }
    return out


def parse_hcpcs(text_: str, stats: LoadStats) -> list[CodeRow]:
    rows: dict[str, CodeRow] = {}
    segments: dict[str, list[str]] = {}
    current: str | None = None
    procedure_records = 0
    layout_failures = 0
    for lineno, line in enumerate(text_.splitlines(), start=1):
        if not line.strip():
            continue
        ref = f"line:{lineno}"
        rec = line.ljust(RECORD_LENGTH)
        code, recid = rec[0:5].strip(), rec[10:11]
        if recid in {"7", "8"}:
            stats.count("modifier_records_skipped")
            current = None
            continue
        if recid not in {"3", "4"}:
            layout_failures += 1
            stats.reject(ref, "record_id", f"unknown record id {recid!r}")
            continue
        if CPT_LIKE.match(code) and not LEVEL2_CODE.match(code):
            stats.count("numeric_codes_skipped")
            current = None
            continue
        if not LEVEL2_CODE.match(code):
            layout_failures += 1
            stats.reject(ref, "code_format", f"{code!r} is not a Level II code")
            current = None
            continue
        long_seg = rec[11:91]
        if recid == "4":
            if current != code:
                layout_failures += 1
                stats.reject(
                    ref, "orphan_continuation", f"{code}: continuation without a first line"
                )
                continue
            segments[code].append(long_seg)
            continue
        procedure_records += 1
        try:
            added = _yyyymmdd(rec[268:276])
            _yyyymmdd(rec[276:284])
            terminated = _yyyymmdd(rec[284:292])
        except ValueError as exc:
            layout_failures += 1
            stats.reject(ref, "date_format", f"{code}: bad date {exc}")
            current = None
            continue
        if code in rows:
            stats.reject(ref, "duplicate_code", f"{code} appears twice; first kept")
            current = None
            continue
        rows[code] = CodeRow(code, "", rec[91:119].strip() or None, added, terminated)
        segments[code] = [long_seg]
        current = code
    if procedure_records == 0:
        raise SourceError("no HCPCS procedure records found; the record layout may have changed")
    undated = sum(1 for r in rows.values() if r.added is None)
    if undated * 2 > len(rows):
        raise SourceError(
            f"{undated} of {len(rows)} codes have no added date in columns 269-276; "
            "the HCPCS record layout may have changed"
        )
    if layout_failures * 1000 > procedure_records * MAX_LAYOUT_FAILURE_PERMILLE:
        raise SourceError(
            f"{layout_failures} layout failures in {procedure_records} records; "
            "the HCPCS record layout may have changed"
        )
    for code, row in rows.items():
        row.long = join_segments(segments[code])
        if row.terminated and row.added and row.terminated < row.added:
            row.terminated = None
            stats.reject(code, "term_before_add", f"{code}: termination before add date ignored")
    stats.rows_in = procedure_records
    return list(rows.values())


def upsert_codes(
    conn: Connection,
    system: CodeSystem,
    version: str,
    rows: list[CodeRow],
    descriptor_source: str,
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> int:
    if system is CodeSystem.CPT:
        raise ValueError("CPT descriptors are not loaded without an AMA licence (D-002)")
    params = [
        {
            "sys": system.value,
            "code": r.code,
            "ver": version,
            "d": r.long or None,
            "ds": r.short,
            "src": descriptor_source,
            "ef": effective_from or r.added,
            "et": effective_to or r.terminated,
        }
        for r in rows
    ]
    if params:
        conn.execute(
            text(
                """
                INSERT INTO ref.code (system, code, version, descriptor, descriptor_short,
                                      descriptor_source, effective_from, effective_to)
                VALUES (CAST(:sys AS ref.code_system), :code, :ver, :d, :ds, :src, :ef, :et)
                ON CONFLICT (system, code, version) DO UPDATE SET
                    descriptor = EXCLUDED.descriptor,
                    descriptor_short = EXCLUDED.descriptor_short,
                    descriptor_source = EXCLUDED.descriptor_source,
                    effective_from = EXCLUDED.effective_from,
                    effective_to = EXCLUDED.effective_to
                """
            ),
            params,
        )
    return len(params)


def load_hcpcs(conn: Connection, text_: str, year: int, descriptor_source: str) -> LoadStats:
    """Version is the HCPCS year; each quarterly file updates that year's rows."""
    stats = LoadStats()
    rows = parse_hcpcs(text_, stats)
    stats.rows_loaded = upsert_codes(conn, CodeSystem.HCPCS, str(year), rows, descriptor_source)
    stats.summary["terminated"] = sum(1 for r in rows if r.terminated)
    return stats


# ------------------------------------------------------------------ MS-DRG
def _tables(name: str, data: bytes) -> list[tuple[str, list[list[str]]]]:
    """(label, rows) per worksheet of an .xlsx, or one table for a text file."""
    if name.lower().endswith(".xlsx"):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out: list[tuple[str, list[list[str]]]] = []
        for ws in wb.worksheets:
            rows = [
                ["" if v is None else str(v).strip() for v in values]
                for values in ws.iter_rows(values_only=True)
            ]
            out.append((ws.title, rows))
        return out
    lines = decode_text(data).splitlines()
    delim = "\t" if sum(ln.count("\t") for ln in lines[:50]) else ","
    return [(name, [[c.strip() for c in r] for r in csv.reader(lines, delimiter=delim)])]


def _find_header(table: list[list[str]]) -> tuple[int, int, int] | None:
    for i, row in enumerate(table[:100]):
        upper = [c.upper().replace("\n", " ") for c in row]
        if "MS-DRG" in upper and any("TITLE" in c for c in upper):
            title_col = next(j for j, c in enumerate(upper) if "TITLE" in c)
            return i, upper.index("MS-DRG"), title_col
    return None


def _is_correction(label: str, table: list[list[str]], header_idx: int) -> bool:
    text = " ".join([label, *(" ".join(r) for r in table[:header_idx])]).upper()
    return "CORRECTION" in text


def _read_table(
    table: list[list[str]], header: tuple[int, int, int], stats: LoadStats
) -> dict[str, CodeRow]:
    header_idx, code_col, title_col = header
    rows: dict[str, CodeRow] = {}
    for i, row in enumerate(table[header_idx + 1 :], start=header_idx + 2):
        if len(row) <= max(code_col, title_col):
            continue
        code, title = row[code_col].strip(), " ".join(row[title_col].split())
        if not code and not title:
            continue
        if re.fullmatch(r"[0-9]{1,3}", code):
            code = code.zfill(3)  # spreadsheet cells drop leading zeros: 1 -> 001
        if not re.fullmatch(r"[0-9]{3}", code) or not title:
            stats.reject(f"row:{i}", "row_format", f"{row[code_col]!r} / {title!r}")
            continue
        if code in rows:
            stats.reject(f"row:{i}", "duplicate_code", f"MS-DRG {code} appears twice")
            continue
        rows[code] = CodeRow(code, title, None, None, None)
    return rows


def parse_table5(name: str, data: bytes, stats: LoadStats) -> list[CodeRow]:
    """Read Table 5. When the workbook holds both the final-rule table and a
    correction-notice table, the correction notice is used (it supersedes the
    final rule) and the number of titles it changed is recorded. Several
    tables with no way to tell which is current is an error, not a guess."""
    found = []
    for label, table in _tables(name, data):
        header = _find_header(table)
        if header is not None:
            found.append((label, table, header))
    if not found:
        raise SourceError(f"{name}: no header row with 'MS-DRG' and a title column")
    if len(found) == 1:
        chosen = found[0]
    else:
        corrections = [f for f in found if _is_correction(f[0], f[1], f[2][0])]
        if len(corrections) != 1:
            raise SourceError(
                f"{name}: {len(found)} MS-DRG tables {[f[0] for f in found]} and "
                f"{len(corrections)} marked as a correction notice; cannot tell which is current"
            )
        chosen = corrections[0]
    rows = _read_table(chosen[1], chosen[2], stats)
    stats.summary["table"] = chosen[0]
    others = [f for f in found if f is not chosen]
    if others:
        other_rows = _read_table(others[0][1], others[0][2], LoadStats())
        stats.summary["superseded_table"] = others[0][0]
        stats.summary["titles_changed_vs_superseded"] = sum(
            1 for c, r in rows.items() if c in other_rows and other_rows[c].long != r.long
        )
        stats.summary["codes_added_vs_superseded"] = len(set(rows) - set(other_rows))
        stats.summary["codes_removed_vs_superseded"] = len(set(other_rows) - set(rows))
    stats.rows_in = len(rows) + len(stats.rejects)
    return list(rows.values())


def pick_table5_member(data: bytes) -> tuple[str, bytes]:
    """Prefer the .xlsx in the Table 5 zip, else a .txt/.csv."""
    members = zip_members(data)
    for ext in (".xlsx", ".txt", ".csv"):
        found = [(n, d) for n, d in members.items() if n.lower().endswith(ext)]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise SourceError(f"several {ext} members in Table 5 zip: {[n for n, _ in found]}")
    raise SourceError(f"no table in Table 5 zip: {sorted(members)}")


def load_msdrg(
    conn: Connection,
    name: str,
    data: bytes,
    grouper_version: int,
    fiscal_year: int,
    descriptor_source: str,
    min_rows: int = 1,
) -> LoadStats:
    """FY N runs October 1 of N-1 to September 30 of N."""
    stats = LoadStats()
    rows = parse_table5(name, data, stats)
    if len(rows) < min_rows:
        raise SourceError(f"only {len(rows)} MS-DRGs parsed; expected at least {min_rows}")
    stats.rows_loaded = upsert_codes(
        conn,
        CodeSystem.MS_DRG,
        f"v{grouper_version}",
        rows,
        descriptor_source,
        effective_from=date(fiscal_year - 1, 10, 1),
        effective_to=date(fiscal_year, 9, 30),
    )
    return stats
