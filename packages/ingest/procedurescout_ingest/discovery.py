"""Phase 2, step 1: find hospital price files through cms-hpt.txt.

CMS requires each hospital (or the health system hosting its file) to publish
https://<site>/cms-hpt.txt: one block per location with the fields
location-name, source-page-url, mrf-url, contact-name and contact-email
("key: value" lines; blocks separated by blank lines). A redirect to the file
is allowed.

Rules:
- Only websites a person approved (ref.facility.website) are visited.
- Every fetch and every block is stored exactly as published
  (src.hpt_txt_fetch / src.hpt_txt_entry), including failures.
- A block is linked to a facility only by an exact name match among usable
  aliases in the same state (resolve_facility_by_name). Unmatched and
  ambiguous names are reported for review, never guessed.
- Each distinct mrf-url becomes a src.transparency_source; it carries a
  facility only when every block listing that URL is matched to the same
  facility (one file listed for an unmatched location stays unassigned).
  Exception: a location a person approved as listed inside that hospital's own
  file (data/reference/hpt_co_listed_locations_reviewed.csv, exact name and
  hospital) is recorded as 'co_listed' and does not block the assignment;
  likewise a facility with an approved campus_of parent listed in the same file
  (the file goes to the parent only).
- Nothing is downloaded here except the small text file itself.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import Connection, text

from procedurescout_core.enums import Severity
from procedurescout_core.facility_repo import (
    FacilityMatchStatus,
    resolve_facility_by_ccn,
    resolve_facility_by_name,
)

from .reference.common import LoadStats, decode_text, read_delimited, require_columns

HPT_FIELDS = ("location-name", "source-page-url", "mrf-url", "contact-name", "contact-email")
MAX_HPT_BYTES = 1024 * 1024
_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class HptEntry:
    index: int
    values: dict[str, str]
    problems: tuple[str, ...] = field(default_factory=tuple)

    def get(self, key: str) -> str | None:
        return self.values.get(key) or None


def parse_hpt_txt(content: str) -> list[HptEntry]:
    """Split a cms-hpt.txt into blocks. Field names are matched without regard
    to case; values are kept as published (trimmed). A new block starts at a
    blank line or at a repeated location-name."""
    blocks: list[tuple[dict[str, str], list[str]]] = []
    current: dict[str, str] = {}
    problems: list[str] = []

    def close() -> None:
        nonlocal current, problems
        if current or problems:
            blocks.append((current, problems))
        current, problems = {}, []

    for raw in content.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line:
            close()
            continue
        key, sep, value = line.partition(":")
        key = key.strip().lower()
        if not sep or key not in HPT_FIELDS:
            problems.append(f"unrecognized line: {line[:120]}")
            continue
        if key == "location-name" and "location-name" in current:
            close()
        if key in current:
            problems.append(f"repeated field {key}")
        current[key] = value.strip()
    close()

    entries: list[HptEntry] = []
    for i, (values, probs) in enumerate(blocks):
        found = list(probs)
        for name in HPT_FIELDS:
            if not values.get(name):
                found.append(f"missing {name}")
        for name in ("source-page-url", "mrf-url"):
            v = values.get(name)
            if v and not _URL.match(v):
                found.append(f"{name} is not a URL")
        email = values.get("contact-email")
        if email and "@" not in email:
            found.append("contact-email is not an email address")
        entries.append(HptEntry(i, values, tuple(found)))
    return entries


@dataclass(frozen=True, slots=True)
class HptFetch:
    site: str
    url: str
    http_status: int | None = None
    final_url: str | None = None
    data: bytes | None = None
    error: str | None = None
    content_source: str = "live"  # or "captured": an approved copy saved from a browser
    captured_at: date | None = None
    captured_from: str | None = None
    copy_reviewed_by: str | None = None
    fetched_via: str = "github"  # or "home_runner": fetched live from Cooper's computer


Fetcher = Callable[[str], HptFetch]
CAPTURED_COLUMNS = (
    "site",
    "file",
    "captured_from",
    "captured_at",
    "captured_by",
    "reviewed_by",
    "reviewed_at",
)


def load_captured_copies(
    base_dir: Path, manifest_text: str, stats: LoadStats
) -> dict[str, HptFetch]:
    """Approved browser-captured cms-hpt.txt copies, keyed by site. Used only
    when the live fetch of that site fails."""
    rows = read_delimited(manifest_text, ",")
    out: dict[str, HptFetch] = {}
    if not rows:
        return out
    require_columns(rows, CAPTURED_COLUMNS, "captured cms-hpt.txt manifest")
    for row in rows:
        site = row["site"].rstrip("/").lower()
        if not row["reviewed_by"] or not row["reviewed_at"]:
            stats.count("captured_copies_unreviewed")
            continue
        path = base_dir / row["file"]
        if path.parent != base_dir or not path.is_file():
            stats.reject(site, "captured_copy_missing", f"{row['file']} not found")
            continue
        out[site] = HptFetch(
            site=site,
            url=f"{site}/cms-hpt.txt",
            http_status=None,
            final_url=row["captured_from"],
            data=path.read_bytes(),
            content_source="captured",
            captured_at=date.fromisoformat(row["captured_at"]),
            captured_from=row["captured_from"],
            copy_reviewed_by=row["reviewed_by"],
        )
    return out


RATE_LIMIT_WAITS = (15, 45)  # seconds; used when a site answers 429 or a 502/503/504
RETRY_STATUSES = frozenset({429, 502, 503, 504})


def _retry_after(value: str | None, default: int) -> int:
    if value and value.strip().isdigit():
        return min(int(value.strip()), 120)
    return default


def http_fetcher(client: httpx.Client, sleep: Callable[[int], None] = time.sleep) -> Fetcher:
    """Plain GET of /cms-hpt.txt with an honest User-Agent. A "too many
    requests" answer (429) or a temporary server error (502/503/504) is retried
    after the site's Retry-After (or a short wait); refusals such as 403 are
    recorded as they are, never worked around."""

    def fetch_once(site: str, url: str) -> tuple[HptFetch, str | None]:
        try:
            buf = bytearray()
            with client.stream("GET", url) as resp:
                final = str(resp.url)
                if resp.status_code != 200:
                    retry = resp.headers.get("retry-after")
                    return HptFetch(site, url, resp.status_code, final, error="HTTP error"), retry
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > MAX_HPT_BYTES:
                        return HptFetch(site, url, 200, final, error="larger than 1 MB"), None
                ctype = resp.headers.get("content-type", "")
        except httpx.HTTPError as exc:
            return HptFetch(site, url, error=f"{type(exc).__name__}: {exc}"), None
        data = bytes(buf)
        head = data[:200].lstrip().lower()
        if "html" in ctype.lower() or head.startswith((b"<!doctype", b"<html")):
            return HptFetch(
                site, url, 200, final, data, error="returned a web page, not a text file"
            ), None
        return HptFetch(site, url, 200, final, data), None

    def fetch(site: str) -> HptFetch:
        url = f"{site}/cms-hpt.txt"
        result, retry_after = fetch_once(site, url)
        for wait in RATE_LIMIT_WAITS:
            if result.http_status not in RETRY_STATUSES:
                break
            sleep(_retry_after(retry_after, wait))
            result, retry_after = fetch_once(site, url)
        return result

    return fetch


def _insert_fetch(conn: Connection, f: HptFetch, entries: int | None) -> uuid.UUID:
    value = conn.execute(
        text(
            """
            INSERT INTO src.hpt_txt_fetch
                (site, url, http_status, final_url, sha256, bytes, error, entries,
                 content_source, captured_at, captured_from, copy_reviewed_by, fetched_via)
            VALUES (:site, :url, :st, :final, :sha, :b, :err, :n,
                    :cs, :cat, :cfrom, :crb, :via)
            RETURNING id
            """
        ),
        {
            "site": f.site,
            "url": f.url,
            "st": f.http_status,
            "final": f.final_url,
            "sha": hashlib.sha256(f.data).hexdigest() if f.data is not None else None,
            "b": len(f.data) if f.data is not None else None,
            "err": f.error,
            "n": entries,
            "cs": f.content_source,
            "cat": f.captured_at,
            "cfrom": f.captured_from,
            "crb": f.copy_reviewed_by,
            "via": f.fetched_via,
        },
    ).scalar_one()
    return uuid.UUID(str(value))


CO_LISTED_COLUMNS = ("location_name", "parent_ccn", "note", "reviewed_by", "reviewed_at")
CoListed = dict[tuple[str, uuid.UUID], str]


def _name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def load_co_listed(conn: Connection, csv_text: str, stats: LoadStats) -> CoListed:
    """Approved (location name, hospital) pairs: the location may appear in that
    hospital's own price file without stopping the file from being assigned.
    Names are compared exactly (spacing and letter case aside)."""
    rows = read_delimited(csv_text, ",")
    out: CoListed = {}
    if not rows:
        return out
    require_columns(rows, CO_LISTED_COLUMNS, "reviewed co-listed locations CSV")
    for i, row in enumerate(rows, start=2):
        if not row["reviewed_by"] or not row["reviewed_at"] or not row["location_name"]:
            stats.count("co_listed_unreviewed")
            continue
        fid = resolve_facility_by_ccn(conn, row["parent_ccn"])
        if fid is None:
            stats.reject(
                f"line:{i}", "co_listed_parent_not_found", f"CCN {row['parent_ccn']!r} not loaded"
            )
            continue
        out[(_name_key(row["location_name"]), fid)] = row["reviewed_by"]
    stats.summary["co_listed_approved"] = len(out)
    return out


def discover(
    conn: Connection,
    state_code: str,
    fetcher: Fetcher,
    captured: dict[str, HptFetch] | None = None,
    home: dict[str, HptFetch] | None = None,
    co_listed: CoListed | None = None,
) -> LoadStats:
    stats = LoadStats()
    # Approved campus children: a file listing a hospital and its approved campus
    # children belongs to the hospital (the children point to the hospital's file).
    campus_parent = {
        uuid.UUID(str(c)): uuid.UUID(str(p))
        for c, p in conn.execute(
            text(
                "SELECT child_facility_id, parent_facility_id FROM ref.facility_relationship "
                "WHERE relationship_type = 'campus_of' AND review_state = 'approved'"
            )
        ).all()
    }

    def owners(fids: set[uuid.UUID]) -> set[uuid.UUID]:
        return {f for f in fids if campus_parent.get(f) not in fids}

    ccn_of = {
        uuid.UUID(str(fid)): ccn
        for fid, ccn in conn.execute(
            text("SELECT id, ccn FROM ref.facility WHERE state_code = :s"), {"s": state_code}
        ).all()
    }
    facilities = conn.execute(
        text(
            "SELECT id, ccn, website FROM ref.facility "
            "WHERE state_code = :s AND website IS NOT NULL ORDER BY website, ccn"
        ),
        {"s": state_code},
    ).all()
    by_site: dict[str, list[tuple[uuid.UUID, str]]] = {}
    for fid, ccn, site in facilities:
        by_site.setdefault(site, []).append((uuid.UUID(str(fid)), ccn))
    stats.summary["sites"] = len(by_site)

    mrf_facilities: dict[str, set[uuid.UUID]] = {}
    mrf_has_unmatched: set[str] = set()
    # unmatched entries per file, kept until we know whom the file belongs to
    pending: dict[str, list[tuple[int, str, str, str]]] = {}
    mrf_ambiguous: set[str] = set()
    named: set[uuid.UUID] = set()
    for site, members in by_site.items():
        fetched = fetcher(site)
        if fetched.error is not None or fetched.data is None:
            _insert_fetch(conn, fetched, None)
            ccns = ", ".join(c for _, c in members)
            home_fetch = (home or {}).get(site)
            if home_fetch is not None and (home_fetch.error is not None or home_fetch.data is None):
                _insert_fetch(conn, home_fetch, None)
                home_note = (
                    f"; from Cooper's computer: {home_fetch.error} "
                    f"(status {home_fetch.http_status})"
                )
                home_fetch = None
            else:
                home_note = ""
            copy = (captured or {}).get(site)
            if home_fetch is not None:
                stats.count("sites_from_home_runner")
                stats.reject(
                    site,
                    "hpt_fetched_from_home_runner",
                    f"GitHub's request failed ({fetched.error}, status {fetched.http_status}); "
                    f"fetched live from Cooper's computer instead",
                    Severity.INFO,
                )
                fetched = home_fetch
            elif copy is None:
                stats.count("sites_failed")
                stats.reject(
                    site,
                    "hpt_fetch_failed",
                    f"{fetched.url}: {fetched.error} (status {fetched.http_status}){home_note}; "
                    f"facilities {ccns}",
                    Severity.WARNING,
                )
                continue
            else:
                stats.count("sites_from_captured_copy")
                stats.reject(
                    site,
                    "hpt_used_captured_copy",
                    f"live fetch failed ({fetched.error}, status {fetched.http_status}); used copy "
                    f"captured {copy.captured_at} from {copy.captured_from}",
                    Severity.INFO,
                )
                fetched = copy
        entries = parse_hpt_txt(decode_text(fetched.data or b""))
        fetch_id = _insert_fetch(conn, fetched, len(entries))
        stats.count("sites_ok")
        if not entries:
            stats.reject(site, "hpt_empty", f"{fetched.url} has no entries", Severity.WARNING)
        for e in entries:
            stats.rows_in += 1
            name = e.get("location-name")
            mrf = e.get("mrf-url")
            usable = bool(name) and bool(mrf) and bool(_URL.match(mrf or ""))
            status = "unmatched" if usable else "invalid"
            facility_id: uuid.UUID | None = None
            if usable and name:
                match = resolve_facility_by_name(conn, name, state_code)
                if match.status is FacilityMatchStatus.MATCHED:
                    status, facility_id = "matched", match.facility_id
                elif match.status is FacilityMatchStatus.AMBIGUOUS:
                    status = "ambiguous"
            entry_id = conn.execute(
                text(
                    """
                    INSERT INTO src.hpt_txt_entry
                        (fetch_id, block_index, location_name, source_page_url, mrf_url,
                         contact_name, contact_email, facility_id, match_status, problems)
                    VALUES (:f, :i, :n, :sp, :m, :cn, :ce, :fac, :st, :p)
                    RETURNING id
                    """
                ),
                {
                    "f": fetch_id,
                    "i": e.index,
                    "n": name,
                    "sp": e.get("source-page-url"),
                    "m": mrf,
                    "cn": e.get("contact-name"),
                    "ce": e.get("contact-email"),
                    "fac": facility_id,
                    "st": status,
                    "p": list(e.problems),
                },
            ).scalar_one()
            if status != "unmatched":
                stats.count(f"entries_{status}")
            detail = f"{site} | {name!r} | {mrf}"
            if e.problems:
                detail += f" | problems: {'; '.join(e.problems)}"
            if status == "matched" and facility_id is not None:
                named.add(facility_id)
                stats.rows_loaded += 1
                ccn = ccn_of.get(facility_id)
                stats.reject(f"ccn:{ccn or '?'}", "hpt_entry_matched", detail, Severity.INFO)
                if mrf:
                    mrf_facilities.setdefault(mrf, set()).add(facility_id)
            elif status == "unmatched" and mrf:
                pending.setdefault(mrf, []).append((int(entry_id), name or "", site, detail))
                mrf_facilities.setdefault(mrf, set())
                mrf_has_unmatched.add(mrf)
            else:
                stats.reject(site, f"hpt_entry_{status}", detail, Severity.INFO)
                if mrf and status != "invalid":
                    mrf_facilities.setdefault(mrf, set())
                    mrf_has_unmatched.add(mrf)
                    mrf_ambiguous.add(mrf)

    # Approved co-listed locations: only when the file's matched locations are
    # all one hospital and every unmatched name is approved for that hospital
    # (an ambiguous name always blocks).
    approved = co_listed or {}
    for mrf, items in pending.items():
        fids = owners(mrf_facilities.get(mrf, set()))
        parent = next(iter(fids)) if len(fids) == 1 else None
        all_approved = parent is not None and all(
            (_name_key(name), parent) in approved for _, name, _, _ in items
        )
        if all_approved and parent is not None and mrf not in mrf_ambiguous:
            for entry_id, _, site, detail in items:
                conn.execute(
                    text(
                        "UPDATE src.hpt_txt_entry SET match_status = 'co_listed', "
                        "co_listed_with = :p WHERE id = :i"
                    ),
                    {"p": parent, "i": entry_id},
                )
                stats.count("entries_co_listed")
                stats.reject(
                    site,
                    "hpt_entry_co_listed",
                    f"{detail} | approved as listed in ccn {ccn_of.get(parent)}'s file",
                    Severity.INFO,
                )
            mrf_has_unmatched.discard(mrf)
        else:
            for _, _, site, detail in items:
                stats.count("entries_unmatched")
                stats.reject(site, "hpt_entry_unmatched", detail, Severity.INFO)

    for mrf, fids in sorted(mrf_facilities.items()):
        if not _URL.match(mrf):
            continue
        top = owners(fids)
        owner = next(iter(top)) if len(top) == 1 and mrf not in mrf_has_unmatched else None
        for child in sorted(fids - top, key=str):
            if owner is not None:
                stats.count("campus_children_in_parent_file")
                stats.reject(
                    f"ccn:{ccn_of.get(child)}",
                    "listed_in_parent_file",
                    f"{mrf} belongs to ccn {ccn_of.get(owner)} (approved campus parent); "
                    "no prices are shown on this facility's own page",
                    Severity.INFO,
                )
        conn.execute(
            text(
                """
                INSERT INTO src.transparency_source (facility_id, url, discovery_method,
                                                     last_checked_at)
                VALUES (:f, :u, 'cms_hpt_txt', now())
                ON CONFLICT (url) DO UPDATE SET last_checked_at = now(),
                    facility_id = COALESCE(src.transparency_source.facility_id,
                                           EXCLUDED.facility_id)
                """
            ),
            {"f": owner, "u": mrf},
        )
        stats.count("sources_with_one_facility" if owner else "sources_shared_or_unmatched")

    for site, members in by_site.items():
        for fid, ccn in members:
            if fid not in named:
                stats.reject(
                    f"ccn:{ccn}",
                    "facility_not_named",
                    f"no cms-hpt.txt entry on {site} matched this facility's names",
                    Severity.WARNING,
                )
    stats.summary["facilities_named"] = len(named)
    return stats


MANUAL_COLUMNS = (
    "ccn",
    "mrf_url",
    "source_page_url",
    "note",
    "evidence",
    "reviewed_by",
    "reviewed_at",
)


def load_manual_sources(conn: Connection, csv_text: str) -> LoadStats:
    """Price-file links a person checked by hand, for hospitals whose cms-hpt.txt
    does not list them. Each must name one facility, a URL, evidence and a reviewer."""
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, MANUAL_COLUMNS, "manual price-file sources CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i} ccn:{row['ccn']}"
        if not row["reviewed_by"] or not row["reviewed_at"]:
            stats.count("unreviewed")
            continue
        if not _URL.match(row["mrf_url"]) or not row["evidence"]:
            stats.reject(ref, "incomplete", "a URL and evidence are required")
            continue
        fid = resolve_facility_by_ccn(conn, row["ccn"])
        if fid is None:
            stats.reject(ref, "facility_not_found", f"CCN {row['ccn']!r} is not loaded")
            continue
        note = (
            f"{row['note']} | evidence: {row['evidence']} | reviewed by {row['reviewed_by']} "
            f"on {row['reviewed_at']}"
        )
        conn.execute(
            text(
                """
                INSERT INTO src.transparency_source (facility_id, url, discovery_method,
                                                     last_checked_at, review_note)
                VALUES (:f, :u, 'manual', now(), :n)
                ON CONFLICT (url) DO UPDATE SET review_note = EXCLUDED.review_note,
                    facility_id = COALESCE(src.transparency_source.facility_id,
                                           EXCLUDED.facility_id)
                """
            ),
            {"f": fid, "u": row["mrf_url"], "n": note},
        )
        stats.rows_loaded += 1
    return stats


def load_home_fetches(base_dir: Path, stats: LoadStats) -> dict[str, HptFetch]:
    """cms-hpt.txt files fetched live from Cooper's computer earlier in the same
    workflow run (scripts/fetch_hpt_home.ps1). Used only for sites whose fetch
    from GitHub's servers fails."""
    import json

    index = base_dir / "fetches.json"
    if not index.is_file():
        return {}
    records = json.loads(index.read_text(encoding="utf-8-sig"))
    if isinstance(records, dict):  # PowerShell writes a single object for one record
        records = [records]
    out: dict[str, HptFetch] = {}
    for rec in records:
        site = str(rec.get("site", "")).rstrip("/").lower()
        if not site.startswith("https://"):
            continue
        data: bytes | None = None
        error = rec.get("error") or None
        file_name = rec.get("file")
        if file_name and error is None:
            path = base_dir / str(file_name)
            if path.parent == base_dir and path.is_file():
                data = path.read_bytes()
                head = data[:200].lstrip().lower()
                if head.startswith((b"<!doctype", b"<html")):
                    error = "returned a web page, not a text file"
            else:
                error = "file missing from home-runner output"
        status = rec.get("http_status")
        out[site] = HptFetch(
            site=site,
            url=str(rec.get("url") or f"{site}/cms-hpt.txt"),
            http_status=int(status) if isinstance(status, int) else None,
            final_url=rec.get("final_url") or None,
            data=data,
            error=str(error) if error else None,
            fetched_via="home_runner",
        )
        stats.count("home_fetches_ok" if data is not None and not error else "home_fetches_failed")
    return out


# ------------------------------------------------------------------ probing
@dataclass(frozen=True, slots=True)
class ProbeResult:
    method: str
    http_status: int | None = None
    final_url: str | None = None
    content_length: int | None = None
    content_type: str | None = None
    last_modified: str | None = None
    error: str | None = None


Prober = Callable[[str], ProbeResult]
# Statuses after which a HEAD answer is not trusted and the headers of a GET are
# read instead. 404 is included because some pricing APIs answer only GET.
NO_HEAD_STATUSES = frozenset({400, 403, 404, 405, 501})


def _length(value: str | None) -> int | None:
    return int(value) if value and value.strip().isdigit() else None


def http_prober(client: httpx.Client, sleep: Callable[[int], None] = time.sleep) -> Prober:
    """Ask for a price file's headers without downloading it: HEAD first; if the
    server does not answer HEAD usefully, a GET whose body is never read."""

    def from_response(method: str, resp: httpx.Response) -> ProbeResult:
        ok = 200 <= resp.status_code < 300
        return ProbeResult(
            method=method,
            http_status=resp.status_code,
            final_url=str(resp.url),
            content_length=_length(resp.headers.get("content-length")) if ok else None,
            content_type=resp.headers.get("content-type") if ok else None,
            last_modified=resp.headers.get("last-modified") if ok else None,
            error=None if ok else "HTTP error",
        )

    def once(url: str) -> ProbeResult:
        try:
            head = client.head(url)
            if head.status_code not in NO_HEAD_STATUSES and not (
                200 <= head.status_code < 300 and head.headers.get("content-length") is None
            ):
                return from_response("HEAD", head)
            with client.stream("GET", url) as resp:  # body is never read
                return from_response("GET-headers", resp)
        except httpx.HTTPError as exc:
            return ProbeResult(method="HEAD", error=f"{type(exc).__name__}: {exc}")

    def probe(url: str) -> ProbeResult:
        result = once(url)
        if result.http_status in RETRY_STATUSES:
            sleep(RATE_LIMIT_WAITS[0])
            result = once(url)
        return result

    return probe


def _megabytes(n: int) -> str:
    whole, rest = divmod(n * 10 // (1024 * 1024), 10)
    return f"{whole}.{rest} MB"


def probe_sources(conn: Connection, prober: Prober, state_code: str | None = None) -> LoadStats:
    """Check the size and date of every price-file URL that belongs to one of our
    facilities (in one state when ``state_code`` is given); download nothing.

    In scope: files assigned to one facility, and files held back because they
    also list locations we could not match (at least one entry in them matched
    one of our facilities). Files that only list out-of-area locations, which
    network-wide cms-hpt.txt files contain, are counted and skipped."""
    stats = LoadStats()
    sources = conn.execute(
        text(
            """
            SELECT s.id, s.url, f.ccn,
                   (SELECT string_agg(DISTINCT mf.ccn, ',' ORDER BY mf.ccn)
                      FROM src.hpt_txt_entry e JOIN ref.facility mf ON mf.id = e.facility_id
                     WHERE e.mrf_url = s.url AND e.match_status = 'matched') AS matched_ccns
            FROM src.transparency_source s LEFT JOIN ref.facility f ON f.id = s.facility_id
            WHERE CAST(:st AS text) IS NULL OR f.state_code = :st
               OR EXISTS (SELECT 1 FROM src.hpt_txt_entry e2
                            JOIN ref.facility f2 ON f2.id = e2.facility_id
                           WHERE e2.mrf_url = s.url AND e2.match_status = 'matched'
                             AND f2.state_code = :st)
            ORDER BY s.url
            """
        ),
        {"st": state_code.upper() if state_code else None},
    ).all()
    total = 0
    for sid, url, ccn, matched_ccns in sources:
        if ccn is None and matched_ccns is None:
            stats.count("probe_skipped_out_of_area")
            continue
        stats.rows_in += 1
        r = prober(url)
        conn.execute(
            text(
                """
                INSERT INTO src.source_probe (source_id, method, http_status, final_url,
                    content_length, content_type, last_modified, error)
                VALUES (:s, :m, :st, :fu, :cl, :ct, :lm, :e)
                """
            ),
            {
                "s": sid,
                "m": r.method,
                "st": r.http_status,
                "fu": r.final_url,
                "cl": r.content_length,
                "ct": r.content_type,
                "lm": r.last_modified,
                "e": r.error,
            },
        )
        who = f"ccn:{ccn}" if ccn else f"held back (matched ccn {matched_ccns})"
        if r.error is not None:
            stats.count("probe_failed")
            stats.reject(
                who, "probe_failed", f"{url} | {r.error} (status {r.http_status})", Severity.WARNING
            )
            continue
        stats.rows_loaded += 1
        size = _megabytes(r.content_length) if r.content_length is not None else "size not reported"
        if r.content_length is not None:
            total += r.content_length
            stats.count("probe_sized")
        else:
            stats.count("probe_size_unknown")
        stats.reject(
            who,
            "probe_ok",
            f"{url} | {size} | type {r.content_type} | last-modified {r.last_modified}",
            Severity.INFO,
        )
    stats.summary["total_reported_bytes"] = total
    stats.summary["total_reported"] = _megabytes(total)
    return stats
