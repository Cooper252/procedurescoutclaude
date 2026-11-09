"""Verify proposed hospital websites by their own cms-hpt.txt (D-048).

Nationally there are about 6,000 hospitals, too many for a person to check
each website. A proposed website (from data/reference/proposed/
website_candidates_<STATE>.csv: ccn,url,source) is accepted automatically
only when the site's /cms-hpt.txt has a location-name that resolves, by exact
approved alias in the same state, to that very hospital. The fetched file is
the evidence. Anything else is reported and left for later; nothing is
guessed.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from urllib.parse import urlparse

from sqlalchemy import Connection, text

from procedurescout_core.facility_repo import resolve_facility_by_name

from .discovery import parse_hpt_txt
from .reference.common import LoadStats

AUTO_REVIEWER = "automatic (the site's cms-hpt.txt names this hospital, D-048)"
Fetch = Callable[[str], tuple[int, str]]  # url -> (status, body)


def _origin(url: str) -> str | None:
    u = url.strip()
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlparse(u)
    if not p.netloc or " " in p.netloc:
        return None
    return f"https://{p.netloc.lower()}"


def verify(conn: Connection, candidates_csv: str, fetch: Fetch, stats: LoadStats) -> LoadStats:
    for i, row in enumerate(csv.DictReader(io.StringIO(candidates_csv)), start=2):
        stats.rows_in += 1
        ccn = (row.get("ccn") or "").strip().upper()
        origin = _origin(row.get("url") or "")
        ref = f"line {i} ccn {ccn}"
        fac = conn.execute(
            text("SELECT id, state_code, website FROM ref.facility WHERE ccn = :c"), {"c": ccn}
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
        names = [n for n in (e.get("location-name") for e in parse_hpt_txt(body)) if n]
        if not any(
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
            {"w": origin, "e": hpt, "r": AUTO_REVIEWER, "f": fac[0]},
        )
        stats.rows_loaded += 1
        stats.count("verified")
    return stats
