"""Price-list templates and uploads (Cooper, 2026-11-11).

A practice downloads a spreadsheet (CSV, opens in Excel or Google Sheets) made
for its kinds of care: our services for those kinds, with their codes and
units filled in, and an empty "your price" column. A practice with more than
one kind (dental + orthodontics + oral surgery) gets every section in one
file. When it uploads the file, every line is checked:

- a known service (by its id, or by code) with a valid price is ready;
- a blank price is skipped (they don't offer it, or don't want to list it);
- an impossible price, an unknown service id or a repeated line is an error,
  shown on its line;
- a line at the bottom with its own name (and code if they have one) is kept
  as a suggestion until staff add that service to our list.

Nothing goes live from the check alone: the practice confirms, then each price
goes to the usual price review (provider_prices.save_listing).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import Connection, text

from . import provider_prices as prices

COLUMNS = (
    "section",
    "service_id",
    "service",
    "unit",
    "codes",
    "your_price",
    "sessions",
    "in_person_or_online",
    "copay",
    "notes",
)
DELIVERY_WORDS = {"": "in_person", "in person": "in_person", "online": "online", "both": "both"}
OWN_ROWS = 10  # empty lines at the bottom for services we don't have yet
MAX_BYTES = 1_000_000
MAX_LINES = 2_000
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TYPE = re.compile(r"^[a-z][a-z_]{1,40}$")
_CODE = re.compile(r"^(CPT|HCPCS|CDT)\s+([0-9A-Za-z.-]{1,12})$", re.I)

UNIT_WORDS = {
    "per_service": "each",
    "per_unit": "per unit",
    "per_area": "per area",
    "per_syringe": "per syringe",
    "per_session": "per session",
    "per_visit": "per visit",
    "per_day": "per day",
    "per_month": "per month",
    "per_tooth": "per tooth",
    "per_quadrant": "per quarter of the mouth",
    "per_arch": "per arch",
    "per_eye": "per eye",
    "per_vial": "per vial",
    "per_injection": "per injection",
}


class TemplateError(ValueError):
    pass


def _types(conn: Connection, provider_types: list[str]) -> list[tuple[str, str]]:
    clean = sorted({t.strip() for t in provider_types if t.strip()})
    if not clean or len(clean) > 10 or any(not _TYPE.match(t) for t in clean):
        raise TemplateError("Choose up to 10 kinds of care.")
    rows = conn.execute(
        text(
            "SELECT code, name FROM ref.provider_type WHERE code = ANY(:t) "
            "AND review_state = 'approved' ORDER BY name"
        ),
        {"t": clean},
    ).all()
    if len(rows) != len(clean):
        raise TemplateError("One of those kinds of care isn't on our list.")
    return [(str(r[0]), str(r[1])) for r in rows]


def template_csv(conn: Connection, provider_types: list[str]) -> str:
    """The price list for these kinds of care, one section per kind. A service
    two chosen kinds share goes in the more specialised section (braces under
    Orthodontist, not Dental office); the broadest section comes first."""
    chosen = _types(conn, provider_types)
    per_type: dict[str, list[tuple[str, str, str, str]]] = {}
    for code, _ in chosen:
        per_type[code] = [
            (str(r[0]), str(r[1]), str(r[2]), str(r[3]))
            for r in conn.execute(
                text(
                    """
                    SELECT p.slug, p.consumer_name, p.unit,
                           coalesce(string_agg(pc.code_system::text || ' ' || pc.code, ' | '
                                               ORDER BY pc.code), '')
                    FROM ref.procedure p
                    JOIN ref.procedure_provider_type t ON t.procedure_id = p.id
                    LEFT JOIN ref.procedure_code pc ON pc.procedure_id = p.id
                    WHERE t.provider_type = :t AND p.review_state = 'approved'
                      AND p.kind = 'service'
                    GROUP BY p.slug, p.consumer_name, p.unit, p.category
                    ORDER BY p.category, p.consumer_name
                    """
                ),
                {"t": code},
            ).all()
        ]
    size = {c: len(v) for c, v in per_type.items()}
    home: dict[str, str] = {}
    for code, rows in per_type.items():
        for slug, *_ in rows:
            if slug not in home or size[code] < size[home[slug]]:
                home[slug] = code
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(COLUMNS)
    for code, name in sorted(chosen, key=lambda c: (-size[c[0]], c[1])):
        for slug, svc, unit, codes in per_type[code]:
            if home[slug] == code:
                w.writerow(
                    [
                        name,
                        slug,
                        svc,
                        UNIT_WORDS.get(unit, unit),
                        codes,
                        "",
                        "1",
                        "in person",
                        "",
                        "",
                    ]
                )
    for _ in range(OWN_ROWS):
        w.writerow(["Your own services", "", "", "", "", "", "1", "in person", "", ""])
    return out.getvalue()


@dataclass(frozen=True, slots=True)
class Line:
    line: int
    status: str  # "ready", "skipped", "error", "suggestion"
    message: str
    service_id: str | None = None
    service: str | None = None
    code_system: str | None = None
    code: str | None = None
    price: str | None = None
    sessions: int = 1


@dataclass(slots=True)
class UploadCheck:
    lines: list[Line] = field(default_factory=list)
    # line number -> (delivery, copay kind, copay amount)
    extras: dict[int, tuple[str, str | None, Decimal | None]] = field(default_factory=dict)

    def count(self, status: str) -> int:
        return sum(1 for x in self.lines if x.status == status)


def check_upload(conn: Connection, csv_text: str) -> UploadCheck:
    if len(csv_text.encode("utf-8", "replace")) > MAX_BYTES:
        raise TemplateError("That file is too large; a price list is usually well under 1 MB.")
    reader = csv.reader(io.StringIO(csv_text.lstrip("﻿")))
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        raise TemplateError("That file is empty.") from None
    need = ("service_id", "service", "your_price")
    if any(h not in header for h in need):
        raise TemplateError(
            "This isn't our price list template (the service_id, service and your_price "
            "columns are missing). Download the template and fill in the your_price column."
        )
    at = {h: i for i, h in enumerate(header)}

    def cell(row: list[str], name: str) -> str:
        i = at.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    known = {
        str(r[0]): str(r[1])
        for r in conn.execute(
            text("SELECT slug, consumer_name FROM ref.procedure WHERE review_state = 'approved'")
        ).all()
    }
    result = UploadCheck()
    seen: set[tuple[str, int, str]] = set()
    for n, row in enumerate(reader, start=2):
        if n > MAX_LINES + 1:
            raise TemplateError(f"Up to {MAX_LINES} lines per upload.")
        slug, name, raw = cell(row, "service_id"), cell(row, "service"), cell(row, "your_price")
        if not raw:
            result.lines.append(Line(n, "skipped", "No price: not listed.", slug or None, name))
            continue
        try:
            sessions = int(cell(row, "sessions") or "1")
            if not 1 <= sessions <= 100:
                raise ValueError
        except ValueError:
            result.lines.append(Line(n, "error", "Sessions must be a whole number from 1 to 100."))
            continue
        how = DELIVERY_WORDS.get(cell(row, "in_person_or_online").lower())
        if how is None:
            result.lines.append(
                Line(n, "error", "In person or online: write 'in person', 'online' or 'both'.")
            )
            continue
        copay = cell(row, "copay").lower()
        try:
            ck, ca = prices.copay_option(
                None if not copay else "standard" if copay.startswith("standard") else "amount",
                copay.replace("$", "").replace(",", "") or None,
            )
        except prices.ProviderPriceError:
            result.lines.append(
                Line(n, "error", "Copay: write 'standard' or an amount like 25, or leave it blank.")
            )
            continue
        result.extras[n] = (how, ck, ca)
        try:
            price = prices.money(raw.replace("$", "").replace(",", ""), "Price")
        except prices.ProviderPriceError as exc:
            result.lines.append(Line(n, "error", str(exc), slug or None, name, price=raw))
            continue
        if slug:
            if not _SLUG.match(slug) or slug not in known:
                result.lines.append(
                    Line(
                        n,
                        "error",
                        "We don't have that service id. Leave service_id as it was in the "
                        "template, or move this line to 'Your own services'.",
                        slug,
                        name,
                        price=str(price),
                    )
                )
                continue
            if (slug, sessions, how) in seen:
                result.lines.append(
                    Line(n, "error", "This service is listed twice.", slug, known[slug])
                )
                continue
            seen.add((slug, sessions, how))
            result.lines.append(
                Line(n, "ready", "Ready.", slug, known[slug], price=str(price), sessions=sessions)
            )
            continue
        # a practice's own line: a name, maybe a code
        if len(name) < 3:
            result.lines.append(Line(n, "error", "Add a name for this service.", price=str(price)))
            continue
        codes = cell(row, "codes")
        m = _CODE.match(codes) if codes else None
        if codes and m is None:
            result.lines.append(
                Line(
                    n,
                    "error",
                    "Write a code like 'CPT 99213' or 'CDT D1110', or leave it blank.",
                    service=name,
                    price=str(price),
                )
            )
            continue
        system, code = (m.group(1).upper(), m.group(2).upper()) if m else (None, None)
        if system and code:
            slug_for_code = conn.execute(
                text(
                    "SELECT p.slug FROM ref.procedure_code pc JOIN ref.procedure p "
                    "ON p.id = pc.procedure_id WHERE pc.code_system::text = :s "
                    "AND pc.code = :c AND p.review_state = 'approved' LIMIT 1"
                ),
                {"s": system, "c": code},
            ).scalar()
            if slug_for_code is not None and (str(slug_for_code), sessions, how) not in seen:
                seen.add((str(slug_for_code), sessions, how))
                result.lines.append(
                    Line(
                        n,
                        "ready",
                        f"Matched by code to our service '{known[str(slug_for_code)]}'.",
                        str(slug_for_code),
                        known[str(slug_for_code)],
                        price=str(price),
                        sessions=sessions,
                    )
                )
                continue
        result.lines.append(
            Line(
                n,
                "suggestion",
                "Not on our list yet: we'll review it and add it, then your price can go live.",
                service=name[:200],
                code_system=system,
                code=code,
                price=str(price),
                sessions=sessions,
            )
        )
    return result


def apply_upload(
    conn: Connection, facility_id: str, account_id: str, check: UploadCheck
) -> dict[str, int]:
    """Send every ready line to price review and keep the suggestions."""
    if check.count("error"):
        raise TemplateError("Fix the lines marked as problems first, then upload again.")
    sent = kept = 0
    for x in check.lines:
        if x.status == "ready" and x.service_id and x.price:
            how, ck, ca = check.extras.get(x.line, ("in_person", None, None))
            prices.save_listing(
                conn,
                facility_id,
                account_id,
                service_slug=x.service_id,
                quantity=x.sessions,
                regular_price=x.price,
                delivery=how,
                copay_kind=ck,
                copay_amount=ca,
            )
            sent += 1
        elif x.status == "suggestion" and x.service and x.price:
            conn.execute(
                text(
                    """
                    INSERT INTO prov.service_suggestion (facility_id, submitted_by, name,
                        code_system, code, price)
                    VALUES (CAST(:f AS uuid), CAST(:a AS uuid), :n, :s, :c, :p)
                    """
                ),
                {
                    "f": facility_id,
                    "a": account_id,
                    "n": x.service,
                    "s": x.code_system,
                    "c": x.code,
                    "p": Decimal(x.price),
                },
            )
            kept += 1
    return {"sent_for_review": sent, "suggestions": kept}
