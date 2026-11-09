"""A practice that isn't in public records asks to be listed (D-052).

Med spas, weight-loss clinics and other offices without a matching
national-provider taxonomy can still be added: the account fills in name,
address and type; a person checks it (website, phone, state license) before
it becomes a facility. On approval the requester manages the new page, and
the location starts at the ZIP's center until the address is geocoded.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Connection, text

MAX_OPEN_PER_ACCOUNT = 5


class ListingError(ValueError):
    """Message is safe to show."""


def request(conn: Connection, account_id: str, f: dict[str, Any]) -> str:
    def s(k: str, lo: int, hi: int, required: bool = True) -> str | None:
        v = str(f.get(k) or "").strip()
        if not v and not required:
            return None
        if not lo <= len(v) <= hi:
            raise ListingError(f"Check the {k.replace('_', ' ')}.")
        return v

    name = s("name", 3, 120)
    addr = s("address_line1", 3, 120)
    city = s("city", 2, 60)
    state = (s("state_code", 2, 2) or "").upper()
    zip5 = s("zip5", 5, 5)
    if not re.fullmatch(r"[A-Z]{2}", state) or not re.fullmatch(r"\d{5}", zip5 or ""):
        raise ListingError("Check the state and ZIP code.")
    phone = s("phone", 7, 25, False)
    if phone and not re.fullmatch(r"[0-9+() .-]{7,25}", phone):
        raise ListingError("Check the phone number.")
    website = s("website", 4, 300, False)
    if website and not re.match(r"^https?://", website):
        website = "https://" + website
    npi = s("npi", 10, 10, False)
    if npi and not re.fullmatch(r"\d{10}", npi):
        raise ListingError("An NPI is 10 digits.")
    ptype = s("provider_type", 2, 40)
    if (
        conn.execute(
            text("SELECT 1 FROM ref.provider_type WHERE code = :c AND review_state = 'approved'"),
            {"c": ptype},
        ).first()
        is None
    ):
        raise ListingError("Choose a type of practice from the list.")
    open_count = conn.execute(
        text(
            "SELECT count(*) FROM prov.listing_request WHERE account_id = :a AND status = 'pending'"
        ),
        {"a": account_id},
    ).scalar_one()
    if int(open_count) >= MAX_OPEN_PER_ACCOUNT:
        raise ListingError("You have several requests waiting already. We'll get to them soon.")
    rid = conn.execute(
        text(
            """
            INSERT INTO prov.listing_request (account_id, name, address_line1, city, state_code,
                zip5, phone, website, provider_type, npi, note)
            VALUES (:a, :n, :ad, :c, :s, :z, :p, :w, :t, :npi, :note) RETURNING id
            """
        ),
        {
            "a": account_id,
            "n": name,
            "ad": addr,
            "c": city,
            "s": state,
            "z": zip5,
            "p": phone,
            "w": website,
            "t": ptype,
            "npi": npi,
            "note": s("note", 0, 500, False),
        },
    ).scalar_one()
    return str(rid)


def decide(
    conn: Connection, request_id: str, reviewer: str, approve: bool, note: str | None
) -> str | None:
    r = conn.execute(
        text(
            "SELECT account_id, name, address_line1, city, state_code, zip5, phone, provider_type, "
            "npi FROM prov.listing_request WHERE id = CAST(:i AS uuid) AND status = 'pending'"
        ),
        {"i": request_id},
    ).first()
    if r is None:
        raise ListingError("That request was already handled.")
    if not approve:
        if not (note or "").strip():
            raise ListingError("Say why, so the practice can fix it.")
        conn.execute(
            text(
                "UPDATE prov.listing_request SET status = 'rejected', reviewed_by = :b, "
                "reviewed_at = now(), review_note = :n WHERE id = CAST(:i AS uuid)"
            ),
            {"b": reviewer, "n": note, "i": request_id},
        )
        return None
    fid = conn.execute(
        text(
            """
            INSERT INTO ref.facility (name, facility_type, address_line1, city, state_code, zip5,
                phone, source_dataset, status, source_updated_at)
            VALUES (:n, 'other', :a, :c, :s, :z, :p, 'provider_request', 'active', now())
            RETURNING id
            """
        ),
        {"n": r[1], "a": r[2], "c": r[3], "s": r[4], "z": r[5], "p": r[6]},
    ).scalar_one()
    conn.execute(
        text(
            """
            UPDATE ref.facility f SET geom = z.geom,
                geocode_source = z.source || ':' || z.gazetteer_year,
                geocode_precision = 'zcta_centroid'
            FROM ref.zcta z WHERE f.id = :f AND z.zcta5 = f.zip5
            """
        ),
        {"f": fid},
    )
    if r[8]:
        conn.execute(
            text(
                "INSERT INTO ref.facility_npi (facility_id, npi, source) VALUES (:f, :n, "
                "'provider_request') ON CONFLICT DO NOTHING"
            ),
            {"f": fid, "n": r[8]},
        )
    conn.execute(
        text(
            "INSERT INTO ref.facility_provider_type (facility_id, provider_type, source) "
            "VALUES (:f, :t, 'reviewer')"
        ),
        {"f": fid, "t": r[7]},
    )
    conn.execute(
        text(
            """
            INSERT INTO prov.membership (account_id, facility_id, role, status, verified_via,
                verified_by, verified_at)
            VALUES (:a, :f, 'owner', 'active', 'manual', :b, now())
            ON CONFLICT (account_id, facility_id) DO NOTHING
            """
        ),
        {"a": r[0], "f": fid, "b": reviewer},
    )
    conn.execute(
        text(
            "UPDATE prov.listing_request SET status = 'approved', facility_id = :f, "
            "reviewed_by = :b, reviewed_at = now(), review_note = :n WHERE id = CAST(:i AS uuid)"
        ),
        {"f": fid, "b": reviewer, "n": note, "i": request_id},
    )
    return str(fid)


def mine(conn: Connection, account_id: str) -> list[dict[str, Any]]:
    return [
        {"id": str(x[0]), "name": x[1], "status": x[2], "review_note": x[3]}
        for x in conn.execute(
            text(
                "SELECT id, name, status, review_note FROM prov.listing_request "
                "WHERE account_id = :a ORDER BY created_at DESC LIMIT 20"
            ),
            {"a": account_id},
        ).all()
    ]
