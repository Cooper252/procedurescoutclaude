"""Provider homepages (D-050): about, links, hours, logo and photos.

Providers edit a draft and submit it; a person reviews it before it shows.
Only one version is ever published per facility; approving a new one retires
the old one. Logos and photos are checked (real PNG, JPEG or WebP, at most
2 MB) and reviewed before they show.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Connection, text

from .object_store import ObjectStore, media_key

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_PHOTOS = 12
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LANGUAGES = (
    "English",
    "Spanish",
    "Tagalog",
    "Chinese",
    "Vietnamese",
    "Korean",
    "Arabic",
    "French",
    "Russian",
    "Portuguese",
    "Hindi",
    "Japanese",
    "German",
    "ASL",
)
ACCESSIBILITY = (
    "wheelchair_access",
    "accessible_parking",
    "accessible_restroom",
    "elevator",
    "interpreter_available",
    "free_parking",
    "public_transit_nearby",
    "evening_hours",
    "weekend_hours",
    "telehealth",
)
_HOURS = re.compile(r"^(closed|([01][0-9]|2[0-3]):[0-5][0-9]-([01][0-9]|2[0-3]):[0-5][0-9])$")
FIELDS = (
    "about",
    "website_url",
    "booking_url",
    "phone",
    "hours",
    "languages",
    "accessibility",
    "insurance_note",
    "social_urls",
)


class PageError(ValueError):
    """A change that can't be saved (message is safe to show)."""


@dataclass(frozen=True, slots=True)
class Profile:
    id: str | None
    status: str
    about: str | None = None
    website_url: str | None = None
    booking_url: str | None = None
    phone: str | None = None
    hours: dict[str, str] = field(default_factory=dict)
    languages: tuple[str, ...] = ()
    accessibility: tuple[str, ...] = ()
    insurance_note: str | None = None
    social_urls: tuple[str, ...] = ()
    review_note: str | None = None


def _url(value: Any, name: str) -> str | None:
    if value in (None, ""):
        return None
    v = str(value).strip()
    if not re.match(r"^https?://", v, re.I):
        v = "https://" + v
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https") or "." not in parsed.netloc or " " in v:
        raise PageError(f"{name} doesn't look like a web address.")
    if len(v) > 300:
        raise PageError(f"{name} is too long.")
    return v


def _text(value: Any, name: str, limit: int) -> str | None:
    if value in (None, ""):
        return None
    v = str(value).strip()
    if len(v) > limit:
        raise PageError(f"{name} must be {limit} characters or fewer.")
    if re.search(r"<\s*script|javascript:", v, re.I):
        raise PageError(f"{name} can't contain code.")
    return v or None


def clean(fields: dict[str, Any]) -> dict[str, Any]:
    """Validate a profile form. Unknown fields are refused."""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise PageError(f"Unknown fields: {', '.join(sorted(unknown))}")
    out: dict[str, Any] = {}
    out["about"] = _text(fields.get("about"), "About", 2000)
    out["website_url"] = _url(fields.get("website_url"), "Website")
    out["booking_url"] = _url(fields.get("booking_url"), "Booking link")
    phone = _text(fields.get("phone"), "Phone", 25)
    if phone and not re.fullmatch(r"[0-9+() .-]{7,25}", phone):
        raise PageError("Phone can only use numbers, spaces and + ( ) - .")
    out["phone"] = phone
    hours = fields.get("hours") or {}
    if not isinstance(hours, dict) or set(hours) - set(DAYS):
        raise PageError("Hours must be given by day (mon to sun).")
    for day, value in hours.items():
        if not isinstance(value, str) or not _HOURS.match(value):
            raise PageError(f"Hours for {day} must look like 08:00-17:00 or 'closed'.")
    out["hours"] = {d: hours[d] for d in DAYS if d in hours}
    langs = list(fields.get("languages") or [])
    if any(lang not in LANGUAGES for lang in langs):
        raise PageError("Pick languages from the list.")
    out["languages"] = sorted(set(langs), key=LANGUAGES.index)
    acc = list(fields.get("accessibility") or [])
    if any(a not in ACCESSIBILITY for a in acc):
        raise PageError("Pick accessibility features from the list.")
    out["accessibility"] = sorted(set(acc), key=ACCESSIBILITY.index)
    out["insurance_note"] = _text(fields.get("insurance_note"), "Insurance note", 500)
    socials = [_url(u, "Social link") for u in (fields.get("social_urls") or [])]
    if len(socials) > 6:
        raise PageError("Up to 6 social links.")
    out["social_urls"] = [u for u in socials if u]
    return out


_COLS = (
    "id, status, about, website_url, booking_url, phone, hours, languages, accessibility, "
    "insurance_note, social_urls, review_note"
)


def _profile(row: Any) -> Profile:
    return Profile(
        id=str(row[0]),
        status=str(row[1]),
        about=row[2],
        website_url=row[3],
        booking_url=row[4],
        phone=row[5],
        hours=dict(row[6] or {}),
        languages=tuple(row[7] or ()),
        accessibility=tuple(row[8] or ()),
        insurance_note=row[9],
        social_urls=tuple(row[10] or ()),
        review_note=row[11],
    )


def editable(conn: Connection, facility_id: str) -> Profile:
    """The open draft (or pending version), else a copy of what is published."""
    for where in ("status IN ('draft', 'pending_review')", "status = 'published'"):
        row = conn.execute(
            text(f"SELECT {_COLS} FROM prov.profile WHERE facility_id = :f AND {where}"),  # noqa: S608
            {"f": facility_id},
        ).first()
        if row is not None:
            return _profile(row)
    return Profile(id=None, status="new")


def last_rejected_note(conn: Connection, facility_id: str) -> str | None:
    note = conn.execute(
        text(
            "SELECT review_note FROM prov.profile WHERE facility_id = :f AND status = 'rejected' "
            "ORDER BY reviewed_at DESC LIMIT 1"
        ),
        {"f": facility_id},
    ).scalar()
    return None if note is None else str(note)


def save_draft(
    conn: Connection, facility_id: str, account_id: str, fields: dict[str, Any], submit: bool
) -> Profile:
    data = clean(fields)
    params = {
        **data,
        "hours": json.dumps(data["hours"]),
        "f": facility_id,
        "a": account_id,
        "st": "pending_review" if submit else "draft",
    }
    row = conn.execute(
        text(
            f"""
            UPDATE prov.profile SET about = :about, website_url = :website_url,
                booking_url = :booking_url, phone = :phone, hours = CAST(:hours AS jsonb),
                languages = :languages, accessibility = :accessibility,
                insurance_note = :insurance_note, social_urls = :social_urls,
                status = :st, submitted_by = :a,
                submitted_at = CASE WHEN :st = 'pending_review' THEN now() END,
                updated_at = now()
            WHERE facility_id = :f AND status IN ('draft', 'pending_review')
            RETURNING {_COLS}
            """  # noqa: S608
        ),
        params,
    ).first()
    if row is None:
        row = conn.execute(
            text(
                f"""
                INSERT INTO prov.profile (facility_id, about, website_url, booking_url, phone,
                    hours, languages, accessibility, insurance_note, social_urls, status,
                    submitted_by, submitted_at)
                VALUES (:f, :about, :website_url, :booking_url, :phone, CAST(:hours AS jsonb),
                    :languages, :accessibility, :insurance_note, :social_urls, :st, :a,
                    CASE WHEN :st = 'pending_review' THEN now() END)
                RETURNING {_COLS}
                """  # noqa: S608
            ),
            params,
        ).first()
    assert row is not None
    return _profile(row)


def review_profile(
    conn: Connection, profile_id: str, reviewer: str, approve: bool, note: str | None
) -> None:
    fid = conn.execute(
        text("SELECT facility_id FROM prov.profile WHERE id = :p AND status = 'pending_review'"),
        {"p": profile_id},
    ).scalar()
    if fid is None:
        raise PageError("That change is no longer waiting for review.")
    if not approve and not (note or "").strip():
        raise PageError("Say why it was not approved, so the provider can fix it.")
    if approve:
        conn.execute(
            text(
                "UPDATE prov.profile SET status = 'superseded' "
                "WHERE facility_id = :f AND status = 'published'"
            ),
            {"f": fid},
        )
    conn.execute(
        text(
            "UPDATE prov.profile SET status = :s, reviewed_by = :r, reviewed_at = now(), "
            "review_note = :n WHERE id = :p"
        ),
        {"s": "published" if approve else "rejected", "r": reviewer, "n": note, "p": profile_id},
    )


# ------------------------------------------------------------------ images
def image_info(data: bytes) -> tuple[str, str, int | None, int | None]:
    """(content type, extension, width, height) for a real PNG, JPEG or WebP."""
    if len(data) > MAX_IMAGE_BYTES:
        raise PageError("Images must be 2 MB or smaller.")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return "image/png", "png", w, h
    if data.startswith(b"\xff\xd8\xff"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return "image/jpeg", "jpg", w, h
            length = struct.unpack(">H", data[i + 2 : i + 4])[0]
            i += 2 + length
        return "image/jpeg", "jpg", None, None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp", None, None
    raise PageError("Upload a PNG, JPEG or WebP image.")


def upload_media(
    conn: Connection,
    store: ObjectStore,
    facility_id: str,
    account_id: str,
    kind: str,
    data: bytes,
    alt_text: str | None,
) -> str:
    if kind not in ("logo", "photo"):
        raise PageError("Choose logo or photo.")
    if not data:
        raise PageError("The file is empty.")
    content_type, ext, width, height = image_info(data)
    if kind == "photo":
        count = conn.execute(
            text(
                "SELECT count(*) FROM prov.media WHERE facility_id = :f AND kind = 'photo' "
                "AND status IN ('pending_review', 'published')"
            ),
            {"f": facility_id},
        ).scalar_one()
        if int(count) >= MAX_PHOTOS:
            raise PageError(f"Up to {MAX_PHOTOS} photos. Remove one first.")
    media_id = uuid.uuid4()
    key = media_key(uuid.UUID(facility_id), media_id, ext)
    alt = _text(alt_text, "Description", 200)
    store.put_media(key, data, content_type)
    conn.execute(
        text(
            """
            INSERT INTO prov.media (id, facility_id, kind, object_key, content_type, bytes,
                sha256, width, height, alt_text, uploaded_by)
            VALUES (:id, :f, :k, :key, :ct, :b, :sha, :w, :h, :alt, :a)
            """
        ),
        {
            "id": media_id,
            "f": facility_id,
            "k": kind,
            "key": key,
            "ct": content_type,
            "b": len(data),
            "sha": hashlib.sha256(data).hexdigest(),
            "w": width,
            "h": height,
            "alt": alt,
            "a": account_id,
        },
    )
    return str(media_id)


def remove_media(conn: Connection, facility_id: str, media_id: str) -> None:
    conn.execute(
        text(
            "UPDATE prov.media SET status = 'removed' WHERE id = CAST(:m AS uuid) "
            "AND facility_id = CAST(:f AS uuid) AND status IN ('pending_review', 'published')"
        ),
        {"m": media_id, "f": facility_id},
    )


def review_media(conn: Connection, media_id: str, reviewer: str, approve: bool) -> None:
    row = conn.execute(
        text(
            "SELECT facility_id, kind FROM prov.media WHERE id = :m AND status = 'pending_review'"
        ),
        {"m": media_id},
    ).first()
    if row is None:
        raise PageError("That image is no longer waiting for review.")
    if approve and row[1] == "logo":
        conn.execute(
            text(
                "UPDATE prov.media SET status = 'removed' WHERE facility_id = :f "
                "AND kind = 'logo' AND status = 'published'"
            ),
            {"f": row[0]},
        )
    conn.execute(
        text(
            "UPDATE prov.media SET status = :s, reviewed_by = :r, reviewed_at = now() WHERE id = :m"
        ),
        {"s": "published" if approve else "rejected", "r": reviewer, "m": media_id},
    )


def media_list(conn: Connection, facility_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, kind, object_key, status, alt_text FROM prov.media WHERE facility_id = :f "
            "AND status IN ('pending_review', 'published', 'rejected') ORDER BY created_at DESC"
        ),
        {"f": facility_id},
    ).all()
    return [
        {"id": str(r[0]), "kind": r[1], "key": r[2], "status": r[3], "alt_text": r[4]} for r in rows
    ]


# --------------------------------------------------------------- public page
@dataclass(frozen=True, slots=True)
class PublicPage:
    claimed: bool
    profile: Profile | None
    logo_key: str | None
    photos: tuple[tuple[str, str | None], ...]
    profile_updated_at: str | None


def public_page(conn: Connection, facility_id: str) -> PublicPage:
    """Reads only the published_* views (works with the public API role)."""
    claimed = (
        conn.execute(
            text("SELECT 1 FROM prov.claimed_facility WHERE facility_id = CAST(:f AS uuid)"),
            {"f": facility_id},
        ).first()
        is not None
    )
    row = conn.execute(
        text(
            "SELECT NULL, 'published', about, website_url, booking_url, phone, hours, languages, "
            "accessibility, insurance_note, social_urls, NULL, updated_at "
            "FROM prov.published_profile WHERE facility_id = CAST(:f AS uuid)"
        ),
        {"f": facility_id},
    ).first()
    media = conn.execute(
        text(
            "SELECT kind, object_key, alt_text FROM prov.published_media "
            "WHERE facility_id = CAST(:f AS uuid) ORDER BY kind, object_key"
        ),
        {"f": facility_id},
    ).all()
    logo = next((str(m[1]) for m in media if m[0] == "logo"), None)
    photos = tuple((str(m[1]), m[2]) for m in media if m[0] == "photo")
    profile = None
    updated = None
    if row is not None:
        p = _profile(row)
        profile = Profile(
            id=None,
            status="published",
            about=p.about,
            website_url=p.website_url,
            booking_url=p.booking_url,
            phone=p.phone,
            hours=p.hours,
            languages=p.languages,
            accessibility=p.accessibility,
            insurance_note=p.insurance_note,
            social_urls=p.social_urls,
        )
        updated = row[12].date().isoformat() if row[12] is not None else None
    return PublicPage(claimed, profile, logo, photos, updated)


def media_is_published(conn: Connection, key: str) -> str | None:
    """Content type of a published image, or None."""
    ct = conn.execute(
        text("SELECT content_type FROM prov.published_media WHERE object_key = :k"), {"k": key}
    ).scalar()
    return None if ct is None else str(ct)
