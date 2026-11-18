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
# price-file headers read for one state's health-system sites in all (each read
# is about 256 KB): keeps the step short before price files start (2026-11-17)
MAX_SIBLING_READS = 400


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


# ------------------------------------------------------- guessed websites
# Vermont run (2026-11-12): 7 of 17 hospitals were on no list of websites we
# use. Hospital domains usually come from the hospital's name ("Copley
# Hospital" -> copleyvt.org, "Northeastern Vermont Regional Hospital" ->
# nvrh.org), so likely domains are tried. A guess is only ever accepted the
# same way as any other candidate: the site's own cms-hpt.txt must name the
# hospital, or its price file's header must give the hospital's address.
_DROP = {"inc", "llc", "the", "corp", "corporation", "co", "dba", "of", "and", "at", "a"}
_KIND = ("hospital", "medical", "center", "centre", "health", "healthcare", "regional",
         "memorial", "community", "general", "system", "services", "clinic")  # fmt: skip
_ABBREV = {"mount": "mt", "saint": "st", "mt": "mount", "st": "saint"}
MAX_GUESSES_PER_HOSPITAL = 24


def guess_origins(name: str, state_code: str) -> list[str]:
    """Likely website addresses for a hospital name, most likely first."""
    words = [w for w in re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split() if w not in _DROP]
    if not words:
        return []
    core = [w for w in words if w not in _KIND]
    upto: list[str] = []
    for w in words:  # "north country hospital and health center" -> up to "hospital"
        upto.append(w)
        if w in ("hospital", "center", "healthcare"):
            break
    st = state_code.lower()
    stems: list[str] = []

    def add(*parts: str) -> None:
        s = "".join(parts)
        if 3 <= len(s) <= 40 and s not in stems:
            stems.append(s)

    add(*upto)
    add(*words)
    if core:
        add(*core)
        add(*core, st)
        add(*core, "health")
        add(*core, "healthcare")
        add(*core, "hospital")
        add(*core, "medical")
        add(*[_ABBREV.get(w, w) for w in core])
    if len(words) >= 2:
        add(*(w[0] for w in words))  # "northeastern vermont regional hospital" -> nvrh
        add(*(w[0] for w in words), st)
    out: list[str] = []
    for s in stems:
        for tld in ("org", "com"):
            out.append(f"https://www.{s}.{tld}")
    return out[:MAX_GUESSES_PER_HOSPITAL]


def guessed_candidates(
    conn: Connection, state_code: str, fetch_many: Callable[[list[str]], dict[str, str]]
) -> str:
    """ccn,url,source CSV of guessed sites whose /cms-hpt.txt answered with a
    usable file, for hospitals that still have no website. fetch_many takes
    cms-hpt.txt addresses and returns the bodies of those that answered 200."""
    rows = conn.execute(
        text(
            "SELECT ccn, name FROM ref.facility WHERE state_code = :s AND ccn IS NOT NULL "
            "AND website IS NULL AND status = 'active' ORDER BY ccn"
        ),
        {"s": state_code},
    ).all()
    wanted: dict[str, list[str]] = {}
    for ccn, name in rows:
        for origin in guess_origins(str(name), state_code):
            wanted.setdefault(f"{origin}/cms-hpt.txt", []).append(str(ccn))
    found = fetch_many(sorted(wanted))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ccn", "url", "source"])
    for url, body in found.items():
        if not parse_hpt_txt(body):
            continue
        for ccn in wanted.get(url, []):
            w.writerow([ccn, url.removesuffix("/cms-hpt.txt"), "guessed from the hospital's name"])
    return out.getvalue()


def listed_candidates(conn: Connection, listed_csv: str, state_code: str) -> str:
    """ccn,url,source CSV from `data/reference/website_candidates.csv` (state,
    name as CMS writes it or "*" for a health system's site, url, evidence) for
    this state's hospitals that still
    have no website (Arizona, 2026-11-17: Abrazo, St. Joseph's, Valleywise and
    others had no website on any list, so their price files were never found).
    A listed site is only a hint: `verify` accepts it by the same automatic
    checks as every other candidate (its cms-hpt.txt names the hospital, or a
    listed price file's header gives the hospital's address)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ccn", "url", "source"])
    for row in csv.DictReader(io.StringIO(listed_csv)):
        if (row.get("state") or "").strip().upper() != state_code:
            continue
        name = " ".join((row.get("name") or "").split()).upper()
        url = (row.get("url") or "").strip()
        if not name or not url:
            continue
        if name == "*":  # a health system's site: see system_sites / sibling_sites
            continue
        ccns = (
            conn.execute(
                text(
                    "SELECT ccn FROM ref.facility WHERE state_code = :s AND ccn IS NOT NULL "
                    "AND website IS NULL AND status = 'active' "
                    "AND upper(regexp_replace(name, '\\s+', ' ', 'g')) = :n"
                ),
                {"s": state_code, "n": name},
            )
            .scalars()
            .all()
        )
        for ccn in ccns:
            w.writerow([ccn, url, "researched list (website_candidates.csv)"])
    return out.getvalue()


def system_sites(listed_csv: str, state_code: str) -> list[str]:
    """Health systems' sites listed with name "*" for this state in
    `website_candidates.csv`: each is read once by `sibling_sites` for all of
    the state's hospitals that have no price file yet."""
    out = []
    for row in csv.DictReader(io.StringIO(listed_csv)):
        if (row.get("state") or "").strip().upper() != state_code:
            continue
        if (row.get("name") or "").strip() != "*":
            continue
        origin = _origin(row.get("url") or "")
        if origin and origin not in out:
            out.append(origin)
    return out


def sibling_sites(
    conn: Connection,
    state_code: str,
    fetch: Fetch,
    stats: LoadStats,
    head: Head | None = None,
    extra_sites: list[str] | None = None,
) -> LoadStats:
    """Hospitals with no price file yet, found on a health system's site that is
    already verified for another hospital in the state (Arizona, 2026-11-17:
    St. Joseph's, Chandler Regional and others are on Dignity Health's site,
    verified for Dignity's Arizona General, under names CMS writes differently).
    Each site's cms-hpt.txt is read once. A listed name that resolves to such a
    hospital gives it the site (D-048). A listed name that resolves to nothing is
    linked by its price file's header address (D-058), only when that address
    belongs to exactly one hospital in the state. `extra_sites`: health systems'
    sites from `website_candidates.csv` (name "*"), checked the same way."""
    sites = list(
        conn.execute(
            text(
                "SELECT DISTINCT website FROM ref.facility WHERE state_code = :s "
                "AND website IS NOT NULL AND facility_type::text LIKE '%hospital' ORDER BY 1"
            ),
            {"s": state_code},
        )
        .scalars()
        .all()
    )
    sites += [x for x in (extra_sites or []) if x not in sites]
    rows = conn.execute(
        text(
            """
            SELECT f.id, f.website, f.address_line1, f.zip5 FROM ref.facility f
            WHERE f.state_code = :s AND f.status = 'active' AND f.ccn IS NOT NULL
              AND f.facility_type::text LIKE '%hospital'
              AND NOT EXISTS (SELECT 1 FROM src.transparency_source t WHERE t.facility_id = f.id)
            """
        ),
        {"s": state_code},
    ).all()
    wanted = {r[0]: r for r in rows}
    all_keys: dict[str, list[Any]] = {}
    for fid, _w, street, zip5 in conn.execute(
        text(
            "SELECT id, website, address_line1, zip5 FROM ref.facility WHERE state_code = :s "
            "AND status = 'active' AND facility_type::text LIKE '%hospital'"
        ),
        {"s": state_code},
    ).all():
        k = address_key(street, zip5)
        if k is not None:
            all_keys.setdefault(k, []).append(fid)
    heads: dict[str, set[str]] = {}
    reads_left = MAX_SIBLING_READS

    def give_site(fid: Any, origin: str, reviewer: str, evidence: str) -> None:
        if wanted[fid][1] is None:
            conn.execute(
                text(
                    "UPDATE ref.facility SET website = :w, website_evidence_url = :e, "
                    "website_reviewed_by = :r, website_reviewed_at = now() "
                    "WHERE id = :f AND website IS NULL"
                ),
                {"w": origin, "e": evidence, "r": reviewer, "f": fid},
            )

    for origin in sites:
        if not wanted:
            break
        hpt = f"{origin}/cms-hpt.txt"
        try:
            status, body = fetch(hpt)
        except Exception as exc:  # network trouble: report and move on
            stats.reject(origin, "fetch_failed", f"{hpt}: {type(exc).__name__}")
            continue
        if status != 200:
            continue
        reads = 0
        for e in parse_hpt_txt(body):
            name, mrf = e.get("location-name"), e.get("mrf-url")
            if not name:
                continue
            stats.rows_in += 1
            hit = resolve_facility_by_name(conn, name, state_code)
            if hit.facility_id is not None:
                if hit.facility_id in wanted:
                    give_site(hit.facility_id, origin, AUTO_REVIEWER, hpt)
                    stats.count("named_on_system_site")
                    stats.rows_loaded += 1
                continue
            if hit.status != "unmatched" or not mrf or head is None:
                continue
            if mrf not in heads:
                if reads >= MAX_FILES_PER_SITE or reads_left <= 0:
                    continue
                reads += 1
                reads_left -= 1
                try:
                    heads[mrf] = header_address_keys(head(mrf))
                except Exception:  # this file just can't vouch
                    heads[mrf] = set()
            owners = {fid for k in heads[mrf] for fid in all_keys.get(k, [])}
            if len(owners) != 1:
                continue
            (fid,) = owners
            if fid not in wanted:
                continue
            add_alias(
                conn,
                fid,
                name,
                alias_type="mrf_name",
                source=mrf[:500],
                match_basis="manual",
                reviewed_by=ADDRESS_REVIEWER,
            )
            give_site(fid, origin, ADDRESS_REVIEWER, mrf)
            stats.count("linked_by_price_file_address")
            stats.rows_loaded += 1
    return stats
