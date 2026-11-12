"""Verify proposed hospital websites by their own cms-hpt.txt (D-048).

Nationally there are about 6,000 hospitals, too many for a person to check
each website. Candidate websites come from a CSV (ccn,url,source) or from the
community-built DoltHub list of hospital homepages (dolthub_candidates). A
candidate is accepted automatically
only when the site's /cms-hpt.txt has a location-name that resolves, by exact
approved alias in the same state, to that very hospital. The fetched file is
the evidence. Anything else is reported and left for later; nothing is
guessed.

Second test (D-058, all-states run 2026-11-10): health systems often list a
hospital under another name ("Providence St Joseph Hospital Eureka" for CMS's
"PROVIDENCE ST JOSEPH HOSPITAL"). Then the first bytes of each listed price
file are read: the CMS template's header states the hospital's street address
(hospital_address). When it gives this hospital's street number and ZIP code,
the site is accepted and the listed name is saved as an approved alias, so the
price file is linked to the hospital. The header is the evidence.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Connection, text

from procedurescout_core.facility_repo import add_alias, resolve_facility_by_name

from .discovery import parse_hpt_txt
from .reference.common import LoadStats

AUTO_REVIEWER = "automatic (the site's cms-hpt.txt names this hospital, D-048)"
ADDRESS_REVIEWER = "automatic (the price file's header gives this hospital's address, D-058)"
Fetch = Callable[[str], tuple[int, str]]  # url -> (status, body)
Head = Callable[[str], bytes]  # url -> the file's first bytes (about 256 KB)
MAX_FILES_PER_SITE = 150


def address_key(street: str | None, zip_code: str | None) -> str | None:
    """Street number + 5-digit ZIP, e.g. '1100|95501'; None when either is missing."""
    num = re.match(r"\s*(\d{1,6})\b", street or "")
    z = re.search(r"\b(\d{5})(?:-\d{4})?\b", zip_code or "")
    return f"{num.group(1)}|{z.group(1)}" if num and z else None


def _address_strings(head: bytes) -> list[str]:
    text_ = head.decode("utf-8", "replace").lstrip("\ufeff")
    found: list[str] = []
    if text_.lstrip().startswith(("{", "[")):
        for m in re.finditer(r'"hospital_address"\s*:\s*(\[[^\]]*\]|"(?:[^"\\]|\\.)*")', text_):
            found += re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
        return found
    rows = list(csv.reader(io.StringIO("\n".join(text_.splitlines()[:2]))))
    if len(rows) == 2:
        for label, value in zip(rows[0], rows[1], strict=False):
            if "hospital_address" in label.strip().casefold():
                found += [v for v in value.split("|") if v.strip()]
    return found


def header_address_keys(head: bytes) -> set[str]:
    """Street-number + ZIP keys of every hospital_address in a price file's header."""
    keys = set()
    for a in _address_strings(head):
        zips = re.findall(r"\b(\d{5})(?:-\d{4})?\b", a)
        k = address_key(a, zips[-1]) if zips else None
        if k:
            keys.add(k)
    return keys


def _origin(url: str) -> str | None:
    u = url.strip()
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlparse(u)
    if not p.netloc or " " in p.netloc:
        return None
    return f"https://{p.netloc.lower()}"


def verify(
    conn: Connection,
    candidates_csv: str,
    fetch: Fetch,
    stats: LoadStats,
    head: Head | None = None,
) -> LoadStats:
    heads: dict[str, set[str]] = {}

    def keys_of(url: str) -> set[str]:
        if url not in heads:
            try:
                heads[url] = header_address_keys(head(url)) if head is not None else set()
            except Exception:  # network trouble: this file just can't vouch
                heads[url] = set()
        return heads[url]

    for i, row in enumerate(csv.DictReader(io.StringIO(candidates_csv)), start=2):
        stats.rows_in += 1
        ccn = (row.get("ccn") or "").strip().upper()
        origin = _origin(row.get("url") or "")
        ref = f"line {i} ccn {ccn}"
        fac = conn.execute(
            text(
                "SELECT id, state_code, website, address_line1, zip5 FROM ref.facility "
                "WHERE ccn = :c"
            ),
            {"c": ccn},
        ).first()
        if fac is None or origin is None:
            stats.reject(ref, "unknown_hospital_or_url", "no such CCN or the URL is not valid")
            continue
        if fac[2]:
            stats.count("already_has_website")
            continue
        hpt = f"{origin}/cms-hpt.txt"
        try:
            status, body = fetch(hpt)
        except Exception as exc:  # network trouble: report and move on
            stats.reject(ref, "fetch_failed", f"{hpt}: {type(exc).__name__}")
            continue
        if status != 200:
            stats.reject(ref, "no_cms_hpt_txt", f"{hpt} answered {status}")
            continue
        entries = parse_hpt_txt(body)
        names = [n for n in (e.get("location-name") for e in entries) if n]
        reviewer, evidence = AUTO_REVIEWER, hpt
        if not any(
            resolve_facility_by_name(conn, n, str(fac[1])).facility_id == fac[0] for n in names
        ):
            mine = address_key(fac[3], fac[4])
            by_address = None
            if head is not None and mine is not None:
                for e in entries[:MAX_FILES_PER_SITE]:
                    name, mrf = e.get("location-name"), e.get("mrf-url")
                    taken = name is not None and resolve_facility_by_name(
                        conn, name, str(fac[1])
                    ).facility_id not in (None, fac[0])
                    if name and mrf and not taken and mine in keys_of(mrf):
                        by_address = (name, mrf)
                        break
            if by_address is not None:
                add_alias(
                    conn,
                    fac[0],
                    by_address[0],
                    alias_type="mrf_name",
                    source=by_address[1][:500],
                    match_basis="manual",
                    reviewed_by=ADDRESS_REVIEWER,
                )
                reviewer, evidence = ADDRESS_REVIEWER, by_address[1]
                stats.count("verified_by_price_file_address")
        if reviewer == AUTO_REVIEWER and not any(
            resolve_facility_by_name(conn, n, str(fac[1])).facility_id == fac[0] for n in names
        ):
            stats.reject(
                ref,
                "hospital_not_named",
                f"{hpt} lists {len(names)} locations but none matches this hospital exactly",
            )
            continue
        conn.execute(
            text(
                "UPDATE ref.facility SET website = :w, website_evidence_url = :e, "
                "website_reviewed_by = :r, website_reviewed_at = now() WHERE id = :f"
            ),
            {"w": origin, "e": evidence, "r": reviewer, "f": fac[0]},
        )
        stats.rows_loaded += 1
        stats.count("verified")
    return stats


# --------------------------------------------------------------- candidates
DOLTHUB_SQL = "https://www.dolthub.com/api/v1alpha1/dolthub/standard-charge-files/main"
DOLTHUB_SOURCE = "dolthub/standard-charge-files (CC BY-SA 4.0)"


def dolthub_candidates(get_json: Callable[[str, dict[str, str]], Any], state_code: str) -> str:
    """Candidate homepages for one state's hospitals from the community-built
    DoltHub list (CC BY-SA 4.0, used only as hints; each is verified by the
    site's own cms-hpt.txt before use). Returns ccn,url,source CSV text."""
    if not re.fullmatch(r"[A-Z]{2}", state_code):
        raise ValueError(f"not a state code: {state_code!r}")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ccn", "url", "source"])
    offset = 0
    while True:
        # state_code is validated above and offset is an int: nothing user-typed
        # the price page's own site too (2026-11-12): some hospitals keep their
        # price page, and so their cms-hpt.txt, on a different site than the
        # homepage the list gives
        q = (
            "SELECT ccn, homepage, standard_charge_file_indirect_url FROM hospitals "
            "WHERE state = '{s}' AND (length(homepage) > 8 "
            "OR length(standard_charge_file_indirect_url) > 8) "
            "ORDER BY ccn LIMIT 500 OFFSET {o}"
        )
        q = q.format(s=state_code, o=int(offset))
        body = get_json(DOLTHUB_SQL, {"q": q})
        rows = (body.get("rows") or []) if isinstance(body, dict) else []
        for r in rows:
            ccn = str(r.get("ccn") or "").strip().upper()
            if not re.fullmatch(r"[0-9A-Z]{6}", ccn):
                continue
            seen: set[str] = set()
            for col in ("homepage", "standard_charge_file_indirect_url"):
                url = str(r.get(col) or "").strip()
                origin = _origin(url) if url else None
                if origin and origin not in seen:
                    seen.add(origin)
                    w.writerow([ccn, url, DOLTHUB_SOURCE])
        if len(rows) < 500:
            break
        offset += 500
    return out.getvalue()
