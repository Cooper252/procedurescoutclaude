"""Provider-entered prices, specials and packages (PRV-02, PRV-08, PRV-09, D-042).

Providers price an approved standard service or an official billing code, for
one visit or a number of sessions. Every new price, change, special and
package waits for a person to approve it. A live price stays live while a
change to it waits (proposed_price), so editing never hides a price.

Shown labeled "From the provider" and never mixed with hospital-file prices
without a label (rule 8). Regular prices count in comparisons; specials never
do (D-042). Money is Decimal, exact as entered; values needing more than cents
are refused.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text

from .money import parse_dollar
from .offers import Offer, OfferError, check, price_with_offer
from .price_store import PublishedPrice

_CODE = re.compile(r"^[0-9A-Za-z.-]{1,12}$")
MAX_LISTINGS = 500
MAX_PACKAGE_ITEMS = 12


class ProviderPriceError(ValueError):
    """A price that can't be saved (message is safe to show)."""


def money(raw: object, name: str = "Price") -> Decimal:
    try:
        value = parse_dollar(raw)
    except ValueError as exc:
        raise ProviderPriceError(f"{name} must be a dollar amount, like 129 or 129.50.") from exc
    if value is None or value <= 0:
        raise ProviderPriceError(f"{name} must be more than $0.")
    if value != value.quantize(Decimal("0.01")):
        raise ProviderPriceError(f"{name} can have at most 2 decimal places (cents).")
    if value > Decimal("10000000"):
        raise ProviderPriceError(f"{name} is too large.")
    return value


def _piece(
    conn: Connection, service_slug: str | None, code_system: str | None, code: str | None
) -> tuple[str | None, str | None, str | None]:
    """(procedure id, code system, code) for one priced piece, validated."""
    if bool(service_slug) == bool(code):
        raise ProviderPriceError("Choose a service from the list, or enter a billing code.")
    if service_slug:
        pid = conn.execute(
            text("SELECT id FROM ref.procedure WHERE slug = :s AND review_state = 'approved'"),
            {"s": service_slug},
        ).scalar()
        if pid is None:
            raise ProviderPriceError("Choose a service from the standard list.")
        return str(pid), None, None
    system = (code_system or "").strip().upper()
    c = (code or "").strip().upper()
    if not _CODE.match(c):
        raise ProviderPriceError("That doesn't look like a billing code.")
    ok = conn.execute(
        text("SELECT 1 FROM ref.code WHERE system::text = :s AND code = :c"), {"s": system, "c": c}
    ).first()
    if ok is None:
        raise ProviderPriceError(f"We don't know the code {system} {c}.")
    return None, system, c


def _qty(quantity: int) -> int:
    if not 1 <= quantity <= 100:
        raise ProviderPriceError("Sessions must be between 1 and 100.")
    return quantity


# ------------------------------------------------------------------ listings
def save_listing(
    conn: Connection,
    facility_id: str,
    account_id: str,
    *,
    service_slug: str | None = None,
    code_system: str | None = None,
    code: str | None = None,
    quantity: int = 1,
    regular_price: object,
) -> str:
    """Add a price or change one. New prices wait for review; a change to a
    live price is proposed and the live price stays until it's approved."""
    pid, system, c = _piece(conn, service_slug, code_system, code)
    q = _qty(quantity)
    price = money(regular_price, "Regular price")
    row = conn.execute(
        text(
            """
            SELECT id, status, regular_price FROM prov.listing_price
            WHERE facility_id = CAST(:f AS uuid) AND quantity = :q
              AND ((CAST(:p AS uuid) IS NOT NULL AND procedure_id = CAST(:p AS uuid))
                   OR (CAST(:c AS text) IS NOT NULL AND code_system::text = :s AND code = :c))
            """
        ),
        {"f": facility_id, "q": q, "p": pid, "s": system, "c": c},
    ).first()
    if row is None:
        count = conn.execute(
            text(
                "SELECT count(*) FROM prov.listing_price WHERE facility_id = CAST(:f AS uuid) "
                "AND status <> 'withdrawn'"
            ),
            {"f": facility_id},
        ).scalar_one()
        if int(count) >= MAX_LISTINGS:
            raise ProviderPriceError(f"Up to {MAX_LISTINGS} prices per location.")
        lid = conn.execute(
            text(
                """
                INSERT INTO prov.listing_price (facility_id, procedure_id, code_system, code,
                    quantity, regular_price, status, submitted_by)
                VALUES (CAST(:f AS uuid), CAST(:p AS uuid), CAST(:s AS ref.code_system), :c, :q,
                        :price, 'pending_review', :a)
                RETURNING id
                """
            ),
            {
                "f": facility_id,
                "p": pid,
                "s": system,
                "c": c,
                "q": q,
                "price": price,
                "a": account_id,
            },
        ).scalar_one()
        return str(lid)
    lid, status, current = row
    if status == "published":
        if Decimal(current) == price:
            conn.execute(
                text(
                    "UPDATE prov.listing_price SET proposed_price = NULL, proposed_at = NULL "
                    "WHERE id = :id"
                ),
                {"id": lid},
            )
        else:
            conn.execute(
                text(
                    "UPDATE prov.listing_price SET proposed_price = :p, proposed_at = now(), "
                    "submitted_by = :a, updated_at = now() WHERE id = :id"
                ),
                {"p": price, "a": account_id, "id": lid},
            )
    else:
        conn.execute(
            text(
                "UPDATE prov.listing_price SET regular_price = :p, status = 'pending_review', "
                "submitted_by = :a, review_note = NULL, updated_at = now() WHERE id = :id"
            ),
            {"p": price, "a": account_id, "id": lid},
        )
    return str(lid)


def withdraw_listing(conn: Connection, facility_id: str, listing_id: str) -> None:
    done = conn.execute(
        text(
            "UPDATE prov.listing_price SET status = 'withdrawn', proposed_price = NULL, "
            "proposed_at = NULL, updated_at = now() WHERE id = CAST(:l AS uuid) "
            "AND facility_id = CAST(:f AS uuid) RETURNING id"
        ),
        {"l": listing_id, "f": facility_id},
    ).first()
    if done is None:
        raise ProviderPriceError("Unknown price.")
    conn.execute(
        text(
            "UPDATE prov.offer SET status = 'withdrawn' WHERE listing_price_id = CAST(:l AS uuid)"
        ),
        {"l": listing_id},
    )


def review_listing(
    conn: Connection, listing_id: str, reviewer: str, approve: bool, note: str | None
) -> None:
    row = conn.execute(
        text("SELECT status, proposed_price FROM prov.listing_price WHERE id = CAST(:l AS uuid)"),
        {"l": listing_id},
    ).first()
    if row is None or not (row[0] == "pending_review" or row[1] is not None):
        raise ProviderPriceError("That price is no longer waiting for review.")
    if not approve and not (note or "").strip():
        raise ProviderPriceError("Say why, so the provider can fix it.")
    if row[1] is not None:  # a change to a live price
        conn.execute(
            text(
                """
                UPDATE prov.listing_price SET
                    regular_price = CASE WHEN :ok THEN proposed_price ELSE regular_price END,
                    proposed_price = NULL, proposed_at = NULL, review_note = :n,
                    reviewed_by = :r, reviewed_at = now()
                WHERE id = CAST(:l AS uuid)
                """
            ),
            {"ok": approve, "n": note, "r": reviewer, "l": listing_id},
        )
        if approve:  # a special must still be lower than the new regular price
            for oid, kind, op, ao in conn.execute(
                text(
                    "SELECT id, kind, offer_price, amount_off FROM prov.offer "
                    "WHERE listing_price_id = CAST(:l AS uuid) AND status <> 'withdrawn'"
                ),
                {"l": listing_id},
            ).all():
                new = conn.execute(
                    text(
                        "SELECT regular_price FROM prov.listing_price WHERE id = CAST(:l AS uuid)"
                    ),
                    {"l": listing_id},
                ).scalar_one()
                if (kind == "special_price" and op >= new) or (kind == "amount_off" and ao >= new):
                    conn.execute(
                        text(
                            "UPDATE prov.offer SET status = 'withdrawn', review_note = "
                            "'Withdrawn: no longer lower than the new regular price' WHERE id = :o"
                        ),
                        {"o": oid},
                    )
        return
    conn.execute(
        text(
            "UPDATE prov.listing_price SET status = :s, review_note = :n, reviewed_by = :r, "
            "reviewed_at = now() WHERE id = CAST(:l AS uuid)"
        ),
        {"s": "published" if approve else "draft", "n": note, "r": reviewer, "l": listing_id},
    )


# -------------------------------------------------------------------- offers
def add_offer(
    conn: Connection,
    facility_id: str,
    listing_id: str,
    *,
    kind: str,
    who: str,
    value: object,
    starts_on: date,
    ends_on: date | None,
    terms: str | None,
) -> str:
    regular = conn.execute(
        text(
            "SELECT regular_price FROM prov.listing_price WHERE id = CAST(:l AS uuid) "
            "AND facility_id = CAST(:f AS uuid) AND status <> 'withdrawn'"
        ),
        {"l": listing_id, "f": facility_id},
    ).scalar()
    if regular is None:
        raise ProviderPriceError("Add the regular price first.")
    t = (terms or "").strip() or None
    if kind == "percent_off":
        try:
            pct = Decimal(str(value).strip().rstrip("%"))
        except Exception as exc:
            raise ProviderPriceError("Percent off must be a number, like 20.") from exc
        offer = Offer(kind, who, starts_on, ends_on, percent_off=pct, terms=t)
    elif kind == "special_price":
        offer = Offer(
            kind, who, starts_on, ends_on, offer_price=money(value, "Special price"), terms=t
        )
    elif kind == "amount_off":
        offer = Offer(
            kind, who, starts_on, ends_on, amount_off=money(value, "Dollars off"), terms=t
        )
    else:
        raise ProviderPriceError("Choose a kind of special.")
    try:
        check(Decimal(regular), offer)
    except OfferError as exc:
        raise ProviderPriceError(str(exc).capitalize() + ".") from exc
    oid = conn.execute(
        text(
            """
            INSERT INTO prov.offer (listing_price_id, kind, who, offer_price, percent_off,
                amount_off, starts_on, ends_on, terms, status)
            VALUES (CAST(:l AS uuid), :k, :w, :op, :pct, :ao, :s, :e, :t, 'pending_review')
            RETURNING id
            """
        ),
        {
            "l": listing_id,
            "k": offer.kind,
            "w": offer.who,
            "op": offer.offer_price,
            "pct": offer.percent_off,
            "ao": offer.amount_off,
            "s": offer.starts_on,
            "e": offer.ends_on,
            "t": offer.terms,
        },
    ).scalar_one()
    return str(oid)


def withdraw_offer(conn: Connection, facility_id: str, offer_id: str) -> None:
    done = conn.execute(
        text(
            "UPDATE prov.offer o SET status = 'withdrawn' FROM prov.listing_price lp "
            "WHERE o.id = CAST(:o AS uuid) AND lp.id = o.listing_price_id "
            "AND lp.facility_id = CAST(:f AS uuid) RETURNING o.id"
        ),
        {"o": offer_id, "f": facility_id},
    ).first()
    if done is None:
        raise ProviderPriceError("Unknown special.")


def review_offer(
    conn: Connection, offer_id: str, reviewer: str, approve: bool, note: str | None
) -> None:
    done = conn.execute(
        text(
            "UPDATE prov.offer SET status = :s, reviewed_by = :r, reviewed_at = now(), "
            "review_note = :n WHERE id = CAST(:o AS uuid) AND status = 'pending_review' "
            "RETURNING id"
        ),
        {"s": "published" if approve else "draft", "r": reviewer, "n": note, "o": offer_id},
    ).first()
    if done is None:
        raise ProviderPriceError("That special is no longer waiting for review.")


# ------------------------------------------------------------------ packages
def save_package(
    conn: Connection,
    facility_id: str,
    *,
    name: str,
    description: str | None,
    price: object,
    items: list[dict[str, Any]],
) -> str:
    n = name.strip()
    if not 3 <= len(n) <= 80:
        raise ProviderPriceError("Package names are 3 to 80 characters.")
    d = (description or "").strip() or None
    if d is not None and len(d) > 500:
        raise ProviderPriceError("Keep the description under 500 characters.")
    if not 1 <= len(items) <= MAX_PACKAGE_ITEMS:
        raise ProviderPriceError(f"A package has 1 to {MAX_PACKAGE_ITEMS} pieces.")
    pieces = [
        (
            *_piece(conn, i.get("service_slug"), i.get("code_system"), i.get("code")),
            _qty(int(i.get("quantity") or 1)),
        )
        for i in items
    ]
    pkg = conn.execute(
        text(
            "INSERT INTO prov.package (facility_id, name, description, price, status) "
            "VALUES (CAST(:f AS uuid), :n, :d, :p, 'pending_review') RETURNING id"
        ),
        {"f": facility_id, "n": n, "d": d, "p": money(price, "Package price")},
    ).scalar_one()
    for pid, system, c, q in pieces:
        conn.execute(
            text(
                "INSERT INTO prov.package_item (package_id, procedure_id, code_system, code, "
                "quantity) "
                "VALUES (:k, CAST(:p AS uuid), CAST(:s AS ref.code_system), :c, :q)"
            ),
            {"k": pkg, "p": pid, "s": system, "c": c, "q": q},
        )
    return str(pkg)


def withdraw_package(conn: Connection, facility_id: str, package_id: str) -> None:
    done = conn.execute(
        text(
            "UPDATE prov.package SET status = 'withdrawn' WHERE id = CAST(:k AS uuid) "
            "AND facility_id = CAST(:f AS uuid) RETURNING id"
        ),
        {"k": package_id, "f": facility_id},
    ).first()
    if done is None:
        raise ProviderPriceError("Unknown package.")


def review_package(
    conn: Connection, package_id: str, reviewer: str, approve: bool, note: str | None
) -> None:
    done = conn.execute(
        text(
            "UPDATE prov.package SET status = :s, reviewed_by = :r, reviewed_at = now(), "
            "review_note = :n WHERE id = CAST(:k AS uuid) AND status = 'pending_review' "
            "RETURNING id"
        ),
        {"s": "published" if approve else "draft", "r": reviewer, "n": note, "k": package_id},
    ).first()
    if done is None:
        raise ProviderPriceError("That package is no longer waiting for review.")


# ------------------------------------------------------------------- reading
def _s(v: Any) -> str | None:
    return None if v is None else format(Decimal(v).normalize(), "f")


def for_provider(conn: Connection, facility_id: str) -> dict[str, Any]:
    """Everything this provider entered, with review status, for the portal."""
    listings = [
        {
            "id": str(r[0]),
            "service_slug": r[1],
            "service_name": r[2],
            "unit": r[3],
            "code_system": r[4],
            "code": r[5],
            "quantity": int(r[6]),
            "regular_price": _s(r[7]),
            "proposed_price": _s(r[8]),
            "status": r[9],
            "review_note": r[10],
            "offers": [],
        }
        for r in conn.execute(
            text(
                """
                SELECT lp.id, p.slug, p.consumer_name, p.unit, lp.code_system::text, lp.code,
                       lp.quantity, lp.regular_price, lp.proposed_price, lp.status, lp.review_note
                FROM prov.listing_price lp LEFT JOIN ref.procedure p ON p.id = lp.procedure_id
                WHERE lp.facility_id = CAST(:f AS uuid) AND lp.status <> 'withdrawn'
                ORDER BY coalesce(p.consumer_name, lp.code), lp.quantity
                """
            ),
            {"f": facility_id},
        ).all()
    ]
    by_id = {x["id"]: x for x in listings}
    for r in conn.execute(
        text(
            """
            SELECT o.id, o.listing_price_id, o.kind, o.who, o.offer_price, o.percent_off,
                   o.amount_off, o.starts_on, o.ends_on, o.terms, o.status, o.review_note
            FROM prov.offer o JOIN prov.listing_price lp ON lp.id = o.listing_price_id
            WHERE lp.facility_id = CAST(:f AS uuid) AND o.status <> 'withdrawn'
            ORDER BY o.created_at
            """
        ),
        {"f": facility_id},
    ).all():
        target = by_id.get(str(r[1]))
        if target is not None:
            target["offers"].append(
                {
                    "id": str(r[0]),
                    "kind": r[2],
                    "who": r[3],
                    "offer_price": _s(r[4]),
                    "percent_off": _s(r[5]),
                    "amount_off": _s(r[6]),
                    "starts_on": r[7].isoformat(),
                    "ends_on": None if r[8] is None else r[8].isoformat(),
                    "terms": r[9],
                    "status": r[10],
                    "review_note": r[11],
                }
            )
    packages = []
    for r in conn.execute(
        text(
            "SELECT id, name, description, price, status, review_note FROM prov.package "
            "WHERE facility_id = CAST(:f AS uuid) AND status <> 'withdrawn' ORDER BY name"
        ),
        {"f": facility_id},
    ).all():
        items = [
            {"service_name": i[0], "code": i[1], "quantity": int(i[2])}
            for i in conn.execute(
                text(
                    "SELECT p.consumer_name, coalesce(i.code_system::text || ' ' || i.code, NULL), "
                    "i.quantity FROM prov.package_item i LEFT JOIN ref.procedure p "
                    "ON p.id = i.procedure_id WHERE i.package_id = :k"
                ),
                {"k": r[0]},
            ).all()
        ]
        packages.append(
            {
                "id": str(r[0]),
                "name": r[1],
                "description": r[2],
                "price": _s(r[3]),
                "status": r[4],
                "review_note": r[5],
                "items": items,
            }
        )
    return {"listings": listings, "packages": packages}


@dataclass(frozen=True, slots=True)
class Special:
    price: Decimal
    regular: Decimal
    who: str
    kind: str
    percent_off: Decimal | None
    ends_on: date | None
    terms: str | None


def _offers(conn: Connection, listing_ids: list[str], today: date) -> dict[str, Special]:
    """Best active special per listing (lowest price), from published views."""
    best: dict[str, Special] = {}
    if not listing_ids:
        return best
    for r in conn.execute(
        text(
            """
            SELECT o.listing_price_id, o.kind, o.who, o.offer_price, o.percent_off, o.amount_off,
                   o.starts_on, o.ends_on, o.terms, l.regular_price
            FROM prov.published_offer o JOIN prov.published_listing l ON l.id = o.listing_price_id
            WHERE o.listing_price_id = ANY(CAST(:ids AS uuid[]))
              AND o.starts_on <= :d AND (o.ends_on IS NULL OR o.ends_on >= :d)
            """
        ),
        {"ids": listing_ids, "d": today},
    ).all():
        regular = Decimal(r[9])
        offer = Offer(
            kind=r[1],
            who=r[2],
            starts_on=r[6],
            ends_on=r[7],
            offer_price=r[3],
            percent_off=r[4],
            amount_off=r[5],
            terms=r[8],
        )
        try:
            pay = price_with_offer(regular, offer)
        except OfferError:
            continue
        key = str(r[0])
        if key not in best or pay < best[key].price:
            best[key] = Special(
                pay, regular, offer.who, offer.kind, offer.percent_off, offer.ends_on, offer.terms
            )
    return best


def search_prices(
    conn: Connection,
    facility_ids: list[str],
    service_slug: str | None,
    code_system: str | None,
    code: str | None,
    today: date,
) -> tuple[dict[str, PublishedPrice], dict[str, Special]]:
    """Published single-visit provider prices for one service or code, shaped
    like hospital prices (price_source 'provider_entered', cash), plus each
    facility's best active special. Reads published views only."""
    if not facility_ids or not (service_slug or (code_system and code)):
        return {}, {}
    rows = conn.execute(
        text(
            """
            SELECT id, facility_id, coalesce(code_system, ''), coalesce(code, ''),
                   regular_price, service_name
            FROM prov.published_listing
            WHERE facility_id = ANY(CAST(:ids AS uuid[])) AND quantity = 1
              AND ((CAST(:slug AS text) IS NOT NULL AND service_slug = :slug)
                   OR (CAST(:c AS text) IS NOT NULL AND code_system = :s AND code = :c))
            """
        ),
        {"ids": facility_ids, "slug": service_slug, "s": (code_system or "").upper(), "c": code},
    ).all()
    prices: dict[str, PublishedPrice] = {}
    listing_of: dict[str, str] = {}
    for lid, fid, system, c, regular, sname in rows:
        f = str(fid)
        have = prices[f].amount if f in prices else None
        if have is not None and have <= Decimal(regular):
            continue
        prices[f] = PublishedPrice(
            facility_id=f,
            price_source="provider_entered",
            code_system=system or "SERVICE",
            code=c or (service_slug or ""),
            description_raw=sname,
            setting=None,
            price_type="discounted_cash",
            payer_name_raw=None,
            plan_name_raw=None,
            amount=Decimal(regular),
            percentage=None,
            algorithm=None,
            methodology=None,
            dataset_version_id="",
        )
        listing_of[f] = str(lid)
    specials = _offers(conn, list(listing_of.values()), today)
    return prices, {f: specials[lid] for f, lid in listing_of.items() if lid in specials}


def public_prices(conn: Connection, facility_id: str, today: date) -> dict[str, Any]:
    """A facility's published provider prices, active specials and packages."""
    try:
        fid = str(uuid.UUID(facility_id))
    except ValueError as exc:
        raise ProviderPriceError("Unknown provider.") from exc
    rows = conn.execute(
        text(
            "SELECT id, service_slug, service_name, unit, code_system, code, quantity, "
            "regular_price, reviewed_at FROM prov.published_listing "
            "WHERE facility_id = CAST(:f AS uuid) ORDER BY coalesce(service_name, code), quantity"
        ),
        {"f": fid},
    ).all()
    specials = _offers(conn, [str(r[0]) for r in rows], today)
    listings = []
    for r in rows:
        s = specials.get(str(r[0]))
        listings.append(
            {
                "service_slug": r[1],
                "service_name": r[2],
                "unit": r[3],
                "code": None if r[5] is None else f"{r[4]} {r[5]}",
                "quantity": int(r[6]),
                "regular_price": _s(r[7]),
                "updated_at": r[8].date().isoformat() if r[8] else None,
                "special": None
                if s is None
                else {
                    "price": _s(s.price),
                    "who": s.who,
                    "percent_off": _s(s.percent_off),
                    "ends_on": None if s.ends_on is None else s.ends_on.isoformat(),
                    "terms": s.terms,
                },
            }
        )
    packages = []
    for k in conn.execute(
        text(
            "SELECT id, name, description, price FROM prov.published_package "
            "WHERE facility_id = CAST(:f AS uuid) ORDER BY name"
        ),
        {"f": fid},
    ).all():
        items = [
            {"service_name": i[0], "code": i[1], "quantity": int(i[2])}
            for i in conn.execute(
                text(
                    "SELECT service_name, "
                    "CASE WHEN code IS NOT NULL THEN code_system || ' ' || code END, "
                    "quantity FROM prov.published_package_item WHERE package_id = :k"
                ),
                {"k": k[0]},
            ).all()
        ]
        packages.append({"name": k[1], "description": k[2], "price": _s(k[3]), "items": items})
    return {"listings": listings, "packages": packages}
