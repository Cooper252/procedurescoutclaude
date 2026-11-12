"""Search published prices by service (or code) near a place (SRCH-06, D-032).

Every filter is checked against lookup tables before any price file is read
(CLAUDE.md rule 12): the service must be approved and only its approved code
links are used; a direct code must exist in ref.code; the provider type must
be approved; the place and radius must be in range. Nothing is substituted:
each price says which code it was published under, and facilities nearby
without published prices are listed with that status instead of a guess.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import Connection, text

from .enums import CodeSystem
from .object_store import ObjectStore
from .plans import PlanError, all_plans_spellings, approved_spellings, matches
from .price_store import PublishedPrice, find_prices
from .pricing import (
    MODE_PRICE_TYPE,
    Badges,
    Headline,
    Typical,
    badges,
    headline,
    percent_change,
    typical,
)
from .provider_prices import Special, search_prices

MAX_RADIUS_MILES = 100
MAX_FACILITIES = 50
METERS_PER_MILE = Decimal("1609.344")
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_CODE = re.compile(r"^[A-Za-z0-9.\-]{1,20}$")
_PTYPE = re.compile(r"^[a-z][a-z_]*$")


class SearchError(ValueError):
    """A filter failed validation; no price was read."""


def _kinds(conn: Connection, provider_type: str | None) -> list[str]:
    """One kind of care or several, comma-separated ("hospital,surgery_center");
    every one must be an approved kind (2026-11-12: visitors can pick several)."""
    kinds = sorted({k.strip() for k in (provider_type or "").split(",") if k.strip()})
    if len(kinds) > 15 or any(not _PTYPE.match(k) for k in kinds):
        raise SearchError(f"unknown provider type: {provider_type!r}")
    if kinds:
        found = conn.execute(
            text(
                "SELECT count(*) FROM ref.provider_type WHERE code = ANY(:k) "
                "AND review_state = 'approved'"
            ),
            {"k": kinds},
        ).scalar_one()
        if int(found) != len(kinds):
            raise SearchError(f"unknown provider type: {provider_type!r}")
    return kinds


@dataclass(frozen=True, slots=True)
class FacilityResult:
    facility_id: str
    name: str
    city: str | None
    state_code: str
    distance_miles: Decimal
    provider_types: tuple[str, ...]
    status: str  # "prices" or "no_published_prices"
    published_at: str | None
    prices: tuple[PublishedPrice, ...] = field(default_factory=tuple)
    headline: Headline | None = None
    badges: Badges = field(default_factory=Badges)
    change_percent: Decimal | None = None  # headline vs the previous published file
    all_plans_rate: bool = False  # plan rates here are the insurer's one rate for all plans
    # insurance search: this place lists no rate for that insurance, so its cash
    # price is shown instead, labeled (Cooper, 2026-11-12)
    no_plan_rate: bool = False
    special: Special | None = None  # provider special on its own regular price (D-042)
    delivery: str | None = None  # provider price: 'in_person', 'online' or 'both'


@dataclass(frozen=True, slots=True)
class SearchResult:
    service_slug: str | None
    service_name: str | None
    unit: str | None
    codes: tuple[str, ...]
    facilities: tuple[FacilityResult, ...]
    note: str | None = None
    mode: str = "cash"
    typical: Typical | None = None
    all_plans_spellings: frozenset[tuple[str, str]] = frozenset()
    code_description: str | None = None  # hospitals' own wording for a searched code


def _codes_for_service(
    conn: Connection, slug: str
) -> tuple[str, str | None, list[tuple[str, str]]]:
    if not _SLUG.match(slug):
        raise SearchError(f"not a service: {slug!r}")
    row = conn.execute(
        text(
            "SELECT id, consumer_name, unit FROM ref.procedure "
            "WHERE slug = :s AND review_state = 'approved'"
        ),
        {"s": slug},
    ).first()
    if row is None:
        raise SearchError(f"unknown service: {slug!r}")
    codes = conn.execute(
        text(
            "SELECT DISTINCT code_system::text, code FROM ref.procedure_code "
            "WHERE procedure_id = :p AND review_state = 'approved' ORDER BY 1, 2"
        ),
        {"p": row[0]},
    ).all()
    return str(row[1]), str(row[2]), [(str(c[0]), str(c[1])) for c in codes]


def _check_code(conn: Connection, code_system: str, code: str) -> tuple[str, str]:
    try:
        system = CodeSystem(code_system)
    except ValueError as exc:
        raise SearchError(f"not a code type: {code_system!r}") from exc
    if not _CODE.match(code):
        raise SearchError(f"not a code: {code!r}")
    known = conn.execute(
        text("SELECT 1 FROM ref.code WHERE system = CAST(:s AS ref.code_system) AND code = :c"),
        {"s": system.value, "c": code},
    ).first()
    if known is None:
        raise SearchError(f"unknown {system.value} code: {code!r}")
    return system.value, code


def search(
    conn: Connection,
    store: ObjectStore,
    *,
    latitude: Decimal,
    longitude: Decimal,
    radius_miles: Decimal,
    service_slug: str | None = None,
    code_system: str | None = None,
    code: str | None = None,
    provider_type: str | None = None,
    max_facilities: int = MAX_FACILITIES,
    mode: str = "cash",
    plan_id: str | None = None,
    payer_raw: str | None = None,
    online_only: bool = False,
) -> SearchResult:
    if (service_slug is None) == (code is None):
        raise SearchError("give either a service or a code, not both")
    if not (Decimal(-90) <= latitude <= Decimal(90)) or not (
        Decimal(-180) <= longitude <= Decimal(180)
    ):
        raise SearchError("latitude/longitude out of range")
    if not (Decimal(1) <= radius_miles <= Decimal(MAX_RADIUS_MILES)):
        raise SearchError(f"radius must be 1 to {MAX_RADIUS_MILES} miles")
    if mode not in MODE_PRICE_TYPE:
        raise SearchError("mode must be cash, list or plan")
    if (mode == "plan") != (plan_id is not None or payer_raw is not None):
        raise SearchError("a plan is needed for plan prices (and only for them)")
    if plan_id is not None and payer_raw is not None:
        raise SearchError("give a plan or an insurer name as written, not both")
    payer_key: str | None = None
    if payer_raw is not None:
        from .matching import normalize_name

        payer_key = normalize_name(payer_raw)
        known = (
            0 < len(payer_key) <= 200
            and conn.execute(
                text("SELECT 1 FROM ref.payer_index WHERE raw_normalized = :k"), {"k": payer_key}
            ).first()
        )
        if not known:
            raise SearchError("unknown insurer name")
    spellings: set[tuple[str, str]] = set()
    fallback: set[tuple[str, str]] = set()
    if plan_id is not None:
        try:
            spellings = approved_spellings(conn, plan_id)
        except PlanError as exc:
            raise SearchError(str(exc)) from exc
        fallback = all_plans_spellings(conn, plan_id)
    if not 1 <= max_facilities <= MAX_FACILITIES:
        raise SearchError(f"max_facilities must be 1 to {MAX_FACILITIES}")
    kinds = _kinds(conn, provider_type)

    name: str | None = None
    unit: str | None = None
    if service_slug is not None:
        name, unit, codes = _codes_for_service(conn, service_slug)
    else:
        codes = [_check_code(conn, code_system or "", code or "")]
    code_description = None
    if service_slug is None:
        code_description = conn.execute(
            text(
                "SELECT hospital_description FROM ref.code_index "
                "WHERE system = CAST(:s AS ref.code_system) AND code = :c"
            ),
            {"s": codes[0][0], "c": codes[0][1]},
        ).scalar()

    facilities = conn.execute(
        text(
            """
            -- Only the places that can answer (a published hospital file, or a
            -- provider price for this service) plus the nearest :n others are
            -- looked at, using the map index (2026-11-12: measuring and checking
            -- every one of thousands of Las Vegas offices took 8-11 seconds).
            WITH p AS (
                SELECT CAST(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS geography) AS pt
            ),
            answers AS (
                SELECT pf.facility_id AS id FROM price.published_file pf
                UNION
                SELECT pl.facility_id FROM prov.published_listing pl
                WHERE pl.service_slug = CAST(:slug AS text)
                   OR pl.code_system || ':' || pl.code = ANY(:codes)
            ),
            cand AS (
                (SELECT f.id FROM ref.facility f, p
                 WHERE f.id IN (SELECT id FROM answers)
                   AND f.geom IS NOT NULL AND f.status = 'active'
                   AND ST_DWithin(f.geom, p.pt, :meters)
                   AND (cardinality(CAST(:kinds AS text[])) = 0 OR EXISTS (
                        SELECT 1 FROM ref.facility_provider_type x
                        WHERE x.facility_id = f.id
                          AND x.provider_type = ANY(CAST(:kinds AS text[])))))
                UNION
                (SELECT f.id FROM ref.facility f, p
                 WHERE f.geom IS NOT NULL AND f.status = 'active'
                   AND ST_DWithin(f.geom, p.pt, :meters)
                   AND (cardinality(CAST(:kinds AS text[])) = 0 OR EXISTS (
                        SELECT 1 FROM ref.facility_provider_type x
                        WHERE x.facility_id = f.id
                          AND x.provider_type = ANY(CAST(:kinds AS text[]))))
                 ORDER BY f.geom <-> p.pt
                 LIMIT :n)
            )
            SELECT f.id, f.name, f.city, f.state_code,
                   round(CAST(ST_Distance(f.geom, p.pt) AS numeric) / :mpm, 1) AS miles,
                   coalesce(array_agg(fpt.provider_type ORDER BY fpt.provider_type)
                            FILTER (WHERE fpt.provider_type IS NOT NULL), '{}') AS types
            FROM cand
            JOIN ref.facility f ON f.id = cand.id
            CROSS JOIN p
            LEFT JOIN ref.facility_provider_type fpt ON fpt.facility_id = f.id
            GROUP BY f.id, f.name, f.city, f.state_code, p.pt, f.geom
            -- places that can answer come first, then the nearest of the rest:
            -- otherwise thousands of nearby offices push the hospitals out of
            -- the first 50 (first live Nevada load, 2026-11-11)
            ORDER BY (f.id IN (SELECT id FROM answers)) DESC, miles, f.name
            LIMIT :n
            """
        ),
        {
            "lat": latitude,
            "lng": longitude,
            "meters": radius_miles * METERS_PER_MILE,
            "mpm": METERS_PER_MILE,
            "kinds": kinds,
            "n": max_facilities,
            "slug": service_slug,
            "codes": [f"{sys_}:{c}" for sys_, c in codes],
        },
    ).all()
    ids = [str(f[0]) for f in facilities]
    published = (
        {
            str(r[0]): r[1].isoformat()
            for r in conn.execute(
                text(
                    "SELECT facility_id, published_at FROM price.published_file "
                    "WHERE facility_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": ids},
            ).all()
        }
        if ids
        else {}
    )
    by_facility: dict[str, list[PublishedPrice]] = {}
    with_files = [i for i in ids if i in published]
    # only the price types this search shows: cash and list for every mode, plus
    # insurer rates when searching by plan or insurer
    wanted_types = ["discounted_cash", "gross"]
    if mode == "plan" or plan_id is not None or payer_key is not None:
        wanted_types.append("negotiated")
    # online visits: only providers who price this service online (hospital
    # files don't say whether a price is for a video visit)
    if with_files and not online_only:
        for system, value in codes:
            for p in find_prices(
                conn,
                store,
                [uuid.UUID(i) for i in with_files],
                system,
                value,
                price_types=wanted_types,
            ):
                by_facility.setdefault(p.facility_id, []).append(p)
    # provider-entered regular prices (reviewed, published), labeled by price_source;
    # their specials are kept apart and never used in comparisons (D-042)
    from datetime import UTC, datetime

    delivery: dict[str, str] = {}
    provider, specials = search_prices(
        conn,
        ids,
        service_slug,
        None if service_slug else codes[0][0] if codes else None,
        None if service_slug else codes[0][1] if codes else None,
        datetime.now(UTC).date(),
        online_only=online_only,
        delivery_out=delivery,
    )
    for fid, p in provider.items():
        by_facility.setdefault(fid, []).append(p)
    uses_all_plans: set[str] = set()
    if plan_id is not None:
        # only this plan's negotiated rates (by approved spellings) plus cash and
        # list prices for comparison; other plans are never shown in its place.
        # Where a hospital published no rate for this plan but one rate for all
        # of the insurer's plans, that rate is used and labeled.
        filtered: dict[str, list[PublishedPrice]] = {}
        for fid, rows in by_facility.items():
            exact = [p for p in rows if p.price_type == "negotiated" and matches(p, spellings)]
            pool = exact or [
                p for p in rows if p.price_type == "negotiated" and matches(p, fallback)
            ]
            if pool and not exact:
                uses_all_plans.add(fid)
            filtered[fid] = [p for p in rows if p.price_type != "negotiated"] + pool
        by_facility = filtered
    if payer_key is not None:
        # rates published under exactly this insurer spelling, shown as written (D-046)
        from .matching import normalize_name

        by_facility = {
            fid: [
                p
                for p in rows
                if p.price_type != "negotiated"
                or (p.payer_name_raw is not None and normalize_name(p.payer_name_raw) == payer_key)
            ]
            for fid, rows in by_facility.items()
        }
    heads = {fid: headline(rows, mode) for fid, rows in by_facility.items()}
    cash_heads = {fid: headline(rows, "cash") for fid, rows in by_facility.items()}
    present = [h for h in heads.values() if h is not None]
    typ = typical(present)  # insurance rates only: cash fallbacks never mix in
    cash_instead = {
        fid
        for fid in by_facility
        if mode == "plan" and heads.get(fid) is None and cash_heads.get(fid) is not None
    }
    previous: dict[str, list[PublishedPrice]] = {}
    if with_files:
        for system, value in codes:
            for p in find_prices(
                conn,
                store,
                [uuid.UUID(i) for i in with_files],
                system,
                value,
                previous=True,
                price_types=wanted_types,
            ):
                previous.setdefault(p.facility_id, []).append(p)

    def change(fid: str) -> Decimal | None:
        now = heads.get(fid)
        rows = previous.get(fid, [])
        if plan_id is not None:
            wanted = fallback if fid in uses_all_plans else spellings
            rows = [p for p in rows if p.price_type != "negotiated" or matches(p, wanted)]
        if payer_key is not None:
            from .matching import normalize_name

            rows = [
                p
                for p in rows
                if p.price_type != "negotiated"
                or (p.payer_name_raw is not None and normalize_name(p.payer_name_raw) == payer_key)
            ]
        before = headline(rows, mode) if rows else None
        if now is None or before is None or now.possible_error or before.possible_error:
            return None
        if before.amount == 0 or before.amount == now.amount:
            return None
        return percent_change(before.amount, now.amount)

    results = tuple(
        FacilityResult(
            facility_id=str(f[0]),
            name=str(f[1]),
            city=f[2],
            state_code=str(f[3]),
            distance_miles=Decimal(f[4]),
            provider_types=tuple(f[5]),
            status="prices" if by_facility.get(str(f[0])) else "no_published_prices",
            published_at=published.get(str(f[0])),
            prices=tuple(by_facility.get(str(f[0]), ())),
            headline=(
                cash_heads.get(str(f[0])) if str(f[0]) in cash_instead else heads.get(str(f[0]))
            ),
            badges=badges(heads.get(str(f[0])), present, typ, cash_heads.get(str(f[0]))),
            no_plan_rate=str(f[0]) in cash_instead,
            change_percent=change(str(f[0])),
            all_plans_rate=str(f[0]) in uses_all_plans,
            special=specials.get(str(f[0])),
            delivery=delivery.get(str(f[0])),
        )
        for f in facilities
        if not online_only or str(f[0]) in delivery
    )
    note = None
    if not codes:
        note = "This service has no billing code; only provider-entered prices can match it."
    return SearchResult(
        service_slug=service_slug,
        service_name=name,
        unit=unit,
        codes=tuple(f"{s} {c}" for s, c in codes),
        facilities=results,
        note=note,
        mode=mode,
        typical=typ,
        all_plans_spellings=frozenset(fallback),
        code_description=code_description,
    )


@dataclass(frozen=True, slots=True)
class Nearby:
    facility_id: str
    name: str
    city: str | None
    state_code: str
    distance_miles: Decimal
    provider_types: tuple[str, ...]


def nearby(
    conn: Connection,
    *,
    latitude: Decimal,
    longitude: Decimal,
    radius_miles: Decimal = Decimal(25),
    provider_type: str | None = None,
    limit: int = MAX_FACILITIES,
) -> list[Nearby]:
    """Active facilities near a place (for the "help paying" check), nearest
    first; no prices are read. Filters are validated like search()."""
    if not (Decimal(-90) <= latitude <= Decimal(90)) or not (
        Decimal(-180) <= longitude <= Decimal(180)
    ):
        raise SearchError("latitude/longitude out of range")
    if not (Decimal(1) <= radius_miles <= Decimal(MAX_RADIUS_MILES)):
        raise SearchError(f"radius must be 1 to {MAX_RADIUS_MILES} miles")
    kinds = _kinds(conn, provider_type)
    rows = conn.execute(
        text(
            """
            WITH p AS (
                SELECT CAST(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS geography) AS pt
            ),
            cand AS (  -- nearest first, straight from the map index (2026-11-12)
                SELECT f.id FROM ref.facility f, p
                WHERE f.geom IS NOT NULL AND f.status = 'active'
                   AND ST_DWithin(f.geom, p.pt, :meters)
                   AND (cardinality(CAST(:kinds AS text[])) = 0 OR EXISTS (
                        SELECT 1 FROM ref.facility_provider_type x
                        WHERE x.facility_id = f.id
                          AND x.provider_type = ANY(CAST(:kinds AS text[]))))
                ORDER BY f.geom <-> p.pt
                LIMIT :n
            )
            SELECT f.id, f.name, f.city, f.state_code,
                   round(CAST(ST_Distance(f.geom, p.pt) AS numeric) / :mpm, 1) AS miles,
                   coalesce(array_agg(fpt.provider_type ORDER BY fpt.provider_type)
                            FILTER (WHERE fpt.provider_type IS NOT NULL), '{}') AS types
            FROM cand
            JOIN ref.facility f ON f.id = cand.id
            CROSS JOIN p
            LEFT JOIN ref.facility_provider_type fpt ON fpt.facility_id = f.id
            GROUP BY f.id, f.name, f.city, f.state_code, p.pt, f.geom
            ORDER BY miles, f.name
            """
        ),
        {
            "lat": latitude,
            "lng": longitude,
            "meters": radius_miles * METERS_PER_MILE,
            "mpm": METERS_PER_MILE,
            "kinds": kinds,
            "n": max(1, min(limit, MAX_FACILITIES)),
        },
    ).all()
    return [Nearby(str(r[0]), str(r[1]), r[2], str(r[3]), Decimal(r[4]), tuple(r[5])) for r in rows]


@dataclass(frozen=True, slots=True)
class Suggestion:
    slug: str
    name: str
    unit: str
    matched: str  # the word that matched (the service name or an approved synonym)
    kind: str = "service"  # or "code": a billing code from published prices (D-045)
    code_system: str | None = None
    code: str | None = None


def suggest(conn: Connection, query: str, limit: int = 8) -> list[Suggestion]:
    """Services for the search box as the person types: approved services whose
    name, or an approved everyday word for them, contains what was typed. The
    person picks one; nothing is substituted behind their back."""
    from .matching import normalize_name

    q = normalize_name(query)
    if len(q) < 2 or len(q) > 60:
        return []
    like = "%" + q.replace("%", "").replace("_", "") + "%"
    rows = conn.execute(
        text(
            """
            SELECT p.slug, p.consumer_name, p.unit, m.matched, min(m.rank) AS r
            FROM ref.procedure p
            JOIN (
                SELECT id AS pid, consumer_name AS matched,
                       CASE WHEN lower(consumer_name) LIKE :prefix THEN 0 ELSE 1 END AS rank
                FROM ref.procedure WHERE lower(consumer_name) LIKE :like
                UNION ALL
                SELECT procedure_id, term,
                       CASE WHEN term_normalized LIKE :prefix THEN 0 ELSE 2 END
                FROM ref.procedure_synonym
                WHERE review_state = 'approved' AND term_normalized LIKE :like
            ) m ON m.pid = p.id
            WHERE p.review_state = 'approved' AND p.slug IS NOT NULL
            GROUP BY p.slug, p.consumer_name, p.unit, m.matched
            ORDER BY r, p.consumer_name
            LIMIT :n
            """
        ),
        {"like": like, "prefix": q + "%", "n": max(1, min(limit, 20))},
    ).all()
    seen: set[str] = set()
    out = []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(str(r[0]))
        out.append(Suggestion(str(r[0]), str(r[1]), str(r[2]), str(r[3])))
    room = max(0, max(1, min(limit, 20)) - len(out))
    if room:
        out.extend(_code_suggestions(conn, query.strip(), q, room))
    return out


_CODE_QUERY = re.compile(r"^[A-Za-z]?\d[A-Za-z0-9.]{2,7}$")


def _code_suggestions(conn: Connection, raw: str, normalized: str, n: int) -> list[Suggestion]:
    """Billing codes from published prices: by number ("70551", "J3420") or by
    the hospitals' own wording, most widely published first."""
    if _CODE_QUERY.match(raw):
        rows = conn.execute(
            text(
                "SELECT system::text, code, hospital_description FROM ref.code_index "
                "WHERE upper(code) LIKE :p ORDER BY facilities DESC, code LIMIT :n"
            ),
            {"p": raw.upper().replace("%", "").replace("_", "") + "%", "n": n},
        ).all()
    elif len(normalized) >= 3:
        rows = conn.execute(
            text(
                """
                SELECT system::text, code, hospital_description FROM ref.code_index
                WHERE to_tsvector('english', coalesce(hospital_description, ''))
                      @@ plainto_tsquery('english', :q)
                ORDER BY facilities DESC, prices DESC, code LIMIT :n
                """
            ),
            {"q": normalized, "n": n},
        ).all()
    else:
        return []
    return [
        Suggestion(
            slug=f"code:{r[0]}:{r[1]}",
            name=str(r[2] or f"{r[0]} {r[1]}"),
            unit="per_service",
            matched=f"{r[0]} {r[1]}",
            kind="code",
            code_system=str(r[0]),
            code=str(r[1]),
        )
        for r in rows
    ]


def payer_suggestions(conn: Connection, query: str, limit: int = 10) -> list[tuple[str, int]]:
    """Insurer names exactly as hospitals wrote them (raw text, number of places)."""
    from .matching import normalize_name

    q = normalize_name(query)
    if len(q) < 2 or len(q) > 60:
        return []
    rows = conn.execute(
        text(
            "SELECT raw_text, facilities FROM ref.payer_index WHERE raw_normalized LIKE :p "
            "ORDER BY facilities DESC, prices DESC LIMIT :n"
        ),
        {"p": "%" + q.replace("%", "").replace("_", "") + "%", "n": max(1, min(limit, 20))},
    ).all()
    return [(str(r[0]), int(r[1])) for r in rows]
