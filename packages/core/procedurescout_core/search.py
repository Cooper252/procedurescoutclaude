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
from .plans import (
    PlanError,
    Spellings,
    all_plans_spellings,
    approved_spellings,
    facility_states,
    insurer_spellings,
    matches,
)
from .price_store import PublishedPrice, find_prices
from .pricing import (
    MODE_PRICE_TYPE,
    Badges,
    Headline,
    Typical,
    badges,
    doctor_fee,
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
    # cash or list search: no cash or list price here, but the place publishes
    # insurance rates for this service (shown as such, never as a cash price;
    # Cooper, 2026-11-14: births showed "no published prices" at hospitals that
    # publish hundreds of insurer rates)
    plan_rates_only: bool = False
    doctor_fee: Headline | None = None  # the doctor's part, published separately
    special: Special | None = None  # provider special on its own regular price (D-042)
    delivery: str | None = None  # provider price: 'in_person', 'online' or 'both'
    # priced under another coding system's code for the same stay (D-066)
    priced_as: tuple[str, ...] = ()
    # why a place shows no price (Cooper, 2026-11-20: "45 hospitals and 9 prices"
    # looked like we couldn't find prices): "prices"; "not_listed" (it posts its
    # prices, but not this procedure); "federal" (VA, military and Indian Health
    # Service hospitals don't have to post prices); "no_file" (we don't have
    # its price list yet)
    reason: str = "prices"
    psychiatric: bool = False


_FEDERAL = re.compile(r"veterans|federal|defense|tribal|indian health", re.IGNORECASE)


def _reason(
    has_price: bool, published_at: str | None, ownership: str | None, ftype: str | None
) -> str:
    """Why a place in the results has no price (see FacilityResult.reason)."""
    if has_price:
        return "prices"
    if published_at is not None:
        return "not_listed"
    if ownership and _FEDERAL.search(ownership):
        return "federal"
    return "no_file"


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
    all_plans_spellings: Spellings = field(default_factory=Spellings)
    code_description: str | None = None  # hospitals' own wording for a searched code
    # a plain name for a searched code: the official MS-DRG/HCPCS title written
    # out, or the hospitals' wording with short forms written out
    code_name: str | None = None
    insurer_unsure: str | None = None  # insurer name when searching all its plans


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
            "SELECT code_system::text, code FROM ref.procedure_code "
            "WHERE procedure_id = :p AND review_state = 'approved' "
            "GROUP BY 1, 2 ORDER BY bool_or(role = 'primary') DESC, 1, 2"
        ),
        {"p": row[0]},
    ).all()
    return str(row[1]), str(row[2]), [(str(c[0]), str(c[1])) for c in codes]


def prefer_own_codes(
    by_facility: dict[str, list[PublishedPrice]], variants: set[tuple[str, str]]
) -> tuple[dict[str, list[PublishedPrice]], dict[str, tuple[str, ...]]]:
    """At each place: the service's own codes if it published any; otherwise
    its prices under another system's code for the same stay, with those codes
    returned so they are labeled (D-066). Never both mixed."""
    out: dict[str, list[PublishedPrice]] = {}
    priced_as: dict[str, tuple[str, ...]] = {}
    for fid, rows in by_facility.items():
        own = [p for p in rows if (p.code_system, p.code) not in variants]
        out[fid] = own or rows
        if rows and not own:
            priced_as[fid] = tuple(sorted({f"{p.code_system} {p.code}" for p in rows}))
    return out, priced_as


def _variant_codes(conn: Connection, slug: str) -> set[tuple[str, str]]:
    """A service's codes for the same stay in another coding system or an older
    version (role 'variant', D-066), e.g. APR-DRG 5601 or MS-DRG 775 for a
    vaginal birth (MS-DRG 807). Used at a place only when it published none
    of the service's own codes, and labeled."""
    rows = conn.execute(
        text(
            """
            SELECT pc.code_system::text, pc.code FROM ref.procedure_code pc
            JOIN ref.procedure p ON p.id = pc.procedure_id
            WHERE p.slug = :s AND pc.review_state = 'approved'
            GROUP BY 1, 2 HAVING NOT bool_or(pc.role = 'primary')
            """
        ),
        {"s": slug},
    ).all()
    return {(str(a), str(b)) for a, b in rows}


def _code_name(conn: Connection, code: tuple[str, str]) -> str | None:
    """A searched code's plain name, the same way the options list names it."""
    from .code_names import drg_plain
    from .code_search import clean_wording, group_for, plain_wording

    system, value = code
    # an approved service for this code (any spelling of it): its plain name
    spellings = [f"{a}:{b}" for a, b in same_code_spellings(conn, [code])]
    service = conn.execute(
        text(
            """
            SELECT p.consumer_name FROM ref.procedure_code pc
            JOIN ref.procedure p ON p.id = pc.procedure_id
            WHERE pc.review_state = 'approved' AND p.review_state = 'approved'
              AND pc.role = 'primary' AND p.kind = 'service'
              AND pc.code_system::text || ':' || pc.code = ANY(:k)
            ORDER BY p.consumer_name LIMIT 1
            """
        ),
        {"k": spellings},
    ).scalar()
    if service:
        return str(service)
    title = conn.execute(
        text(
            "SELECT descriptor FROM ref.code WHERE system = CAST(:s AS ref.code_system) "
            "AND code = :c AND descriptor IS NOT NULL AND system IN ('MS-DRG', 'HCPCS') "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"s": system, "c": value},
    ).scalar()
    if title:
        return drg_plain(str(title)) if system == "MS-DRG" else clean_wording(str(title))
    wording = conn.execute(
        text(
            "SELECT hospital_description FROM ref.code_index "
            "WHERE system = CAST(:s AS ref.code_system) AND code = :c"
        ),
        {"s": system, "c": value},
    ).scalar()
    cleaned = clean_wording(str(wording)) if wording else None
    if not cleaned:
        return None
    return drg_plain(cleaned) if group_for(system, value) == "stay" else plain_wording(cleaned)


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


def same_code_spellings(conn: Connection, codes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The same code as hospitals write it (D-065): a CPT number with or
    without its leading zeros ("01967" and "1967") and labeled CPT or HCPCS
    (CPT is HCPCS Level I); an MS-DRG number written "64" or "064";
    an APR-DRG group and severity written "5601", "560-1" or "560.1". Only
    spellings in published prices (ref.code) are added. A different number is
    never added."""
    out = list(codes)
    wanted: list[tuple[str, str]] = []

    def want(sys2: str, spelled: str) -> None:
        if (sys2, spelled) not in out and (sys2, spelled) not in wanted:
            wanted.append((sys2, spelled))

    for system, code in codes:
        if system in ("CPT", "HCPCS") and code.isdigit() and len(code) <= 5:
            bare = code.lstrip("0") or "0"
            for spelled in {bare, bare.zfill(5)}:
                for sys2 in ("CPT", "HCPCS"):
                    want(sys2, spelled)
        elif system == "MS-DRG" and code.isdigit() and len(code) <= 3:
            # "64" and "064" (the plain "DRG" label is not assumed to be MS-DRG:
            # it can be another grouper's number)
            bare = code.lstrip("0") or "0"
            for spelled in {bare, bare.zfill(3)}:
                want("MS-DRG", spelled)
        elif system in ("CDT", "HCPCS") and re.fullmatch(r"[Dd]\d{4}", code):
            # dental codes are HCPCS D-codes; files label them either way
            for sys2 in ("CDT", "HCPCS"):
                want(sys2, code.upper())
        elif system == "APR-DRG":
            # group 560, severity 1: "5601", "560-1" or "560.1"
            m = re.fullmatch(r"(\d{3})[-.]?([1-4])", code)
            if m:
                for spelled in (f"{m[1]}{m[2]}", f"{m[1]}-{m[2]}", f"{m[1]}.{m[2]}"):
                    want("APR-DRG", spelled)
    if wanted:
        # matched on (system, code) so the lookup uses ref.code's index (2026-11-23:
        # the old "system || ':' || code" form read all of ref.code, 2-10 s live)
        found = conn.execute(
            text(
                "SELECT DISTINCT c.system::text, c.code FROM unnest(CAST(:s AS text[]), "
                "CAST(:c AS text[])) AS w(s, c) JOIN ref.code c "
                "ON c.system = CAST(w.s AS ref.code_system) AND c.code = w.c"
            ),
            {"s": [a for a, _ in wanted], "c": [b for _, b in wanted]},
        ).all()
        known = {(str(a), str(b)) for a, b in found}
        out.extend(w for w in wanted if w in known)
    return out


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
    payer_id: str | None = None,
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
    chosen = [x for x in (plan_id, payer_raw, payer_id) if x is not None]
    if (mode == "plan") != bool(chosen):
        raise SearchError("a plan is needed for plan prices (and only for them)")
    if len(chosen) > 1:
        raise SearchError("give one plan, insurer or insurer name as written, not several")
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
    spellings = Spellings()
    fallback = Spellings()
    if plan_id is not None:
        try:
            spellings = approved_spellings(conn, plan_id)
        except PlanError as exc:
            raise SearchError(str(exc)) from exc
        fallback = all_plans_spellings(conn, plan_id)
    insurer_name: str | None = None
    if payer_id is not None:
        # "not sure which plan": every approved work and individual plan of this
        # insurer; shown as a range and labeled, never as one plan's price
        try:
            insurer_name, spellings = insurer_spellings(conn, payer_id)
        except PlanError as exc:
            raise SearchError(str(exc)) from exc
    if not 1 <= max_facilities <= MAX_FACILITIES:
        raise SearchError(f"max_facilities must be 1 to {MAX_FACILITIES}")
    kinds = _kinds(conn, provider_type)

    name: str | None = None
    unit: str | None = None
    if service_slug is not None:
        name, unit, codes = _codes_for_service(conn, service_slug)
        kinds_from_service = not kinds
        if not kinds:
            # only the kinds of place that offer this service (Cooper, 2026-11-17:
            # a birth search near Phoenix listed chiropractors and pharmacies as
            # "doesn't post prices", and they took places in the first 50)
            kinds = sorted(
                str(t)
                for t in conn.execute(
                    text(
                        "SELECT t.provider_type FROM ref.procedure_provider_type t "
                        "JOIN ref.procedure p ON p.id = t.procedure_id WHERE p.slug = :s"
                    ),
                    {"s": service_slug},
                ).scalars()
            )
    else:
        kinds_from_service = False
        codes = [_check_code(conn, code_system or "", code or "")]
    # the same number written another way ("1967" for 01967) is the same code
    variants: set[tuple[str, str]] = set()
    if service_slug is not None:
        variants = set(same_code_spellings(conn, sorted(_variant_codes(conn, service_slug))))
    codes = same_code_spellings(conn, codes)
    code_description = None
    if service_slug is None:
        code_description = conn.execute(
            text(
                "SELECT hospital_description FROM ref.code_index "
                "WHERE system = CAST(:s AS ref.code_system) AND code = :c"
            ),
            {"s": codes[0][0], "c": codes[0][1]},
        ).scalar()

    # online visits (Cooper, 2026-11-12): distance doesn't matter for a video
    # visit, but clinicians are licensed by state, so the whole state is searched
    online_state: str | None = None
    if online_only:
        online_state = conn.execute(
            text(
                "SELECT state_code FROM ref.zcta "
                "ORDER BY geom <-> CAST(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS geography) "
                "LIMIT 1"
            ),
            {"lat": latitude, "lng": longitude},
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
            listed AS (
                SELECT pl.facility_id AS id FROM prov.published_listing pl
                WHERE pl.service_slug = CAST(:slug AS text)
                   OR pl.code_system || ':' || pl.code = ANY(:codes)
            ),
            answers AS (
                SELECT pf.facility_id AS id FROM price.published_file pf
                WHERE CAST(:ostate AS text) IS NULL
                UNION
                SELECT id FROM listed
            ),
            cand AS (
                (SELECT f.id FROM ref.facility f, p
                 WHERE f.id IN (SELECT id FROM answers)
                   AND f.geom IS NOT NULL AND f.status = 'active'
                   AND (CASE WHEN CAST(:ostate AS text) IS NULL
                             THEN ST_DWithin(f.geom, p.pt, :meters)
                             ELSE f.state_code = CAST(:ostate AS text) END)
                   -- a practice that priced this very service always counts
                   AND (cardinality(CAST(:kinds AS text[])) = 0
                        OR (CAST(:kinds_from_service AS boolean) AND (
                            f.id IN (SELECT id FROM listed)
                            OR NOT EXISTS (SELECT 1 FROM ref.facility_provider_type y
                                           WHERE y.facility_id = f.id)))
                        OR EXISTS (
                        SELECT 1 FROM ref.facility_provider_type x
                        WHERE x.facility_id = f.id
                          AND x.provider_type = ANY(CAST(:kinds AS text[])))))
                UNION
                (SELECT f.id FROM ref.facility f, p
                 WHERE CAST(:ostate AS text) IS NULL
                   AND f.geom IS NOT NULL AND f.status = 'active'
                   AND ST_DWithin(f.geom, p.pt, :meters)
                   -- a place whose kind isn't known yet is not left out
                   AND (cardinality(CAST(:kinds AS text[])) = 0
                        OR (CAST(:kinds_from_service AS boolean) AND NOT EXISTS (
                            SELECT 1 FROM ref.facility_provider_type y
                            WHERE y.facility_id = f.id))
                        OR EXISTS (
                        SELECT 1 FROM ref.facility_provider_type x
                        WHERE x.facility_id = f.id
                          AND x.provider_type = ANY(CAST(:kinds AS text[]))))
                 ORDER BY f.geom <-> p.pt
                 LIMIT :n)
            )
            SELECT f.id, f.name, f.city, f.state_code,
                   round(CAST(ST_Distance(f.geom, p.pt) AS numeric) / :mpm, 1) AS miles,
                   coalesce(array_agg(fpt.provider_type ORDER BY fpt.provider_type)
                            FILTER (WHERE fpt.provider_type IS NOT NULL), '{}') AS types,
                   f.facility_type::text AS ftype, f.ownership
            FROM cand
            JOIN ref.facility f ON f.id = cand.id
            CROSS JOIN p
            LEFT JOIN ref.facility_provider_type fpt ON fpt.facility_id = f.id
            GROUP BY f.id, f.name, f.city, f.state_code, p.pt, f.geom, f.facility_type, f.ownership
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
            "kinds_from_service": kinds_from_service,
            "n": max_facilities,
            "slug": service_slug,
            "codes": [f"{sys_}:{c}" for sys_, c in codes],
            "ostate": online_state if online_only else None,
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
    # insurance spellings are matched as they are in each place's state (0027)
    st = facility_states(conn, ids)
    # only the price types this search shows: cash and list for every mode, plus
    # insurer rates when searching by plan or insurer
    wanted_types = ["discounted_cash", "gross"]
    if mode == "plan":
        wanted_types.append("negotiated")
    # online visits: only providers who price this service online (hospital
    # files don't say whether a price is for a video visit)
    # cash and list searches also read insurer rates, only to say that a place
    # publishes them; they are dropped before anything is shown or compared
    read_types = wanted_types if mode == "plan" else [*wanted_types, "negotiated"]
    has_plan_rates: set[str] = set()
    if with_files and not online_only:
        for system, value in codes:
            for p in find_prices(
                conn,
                store,
                [uuid.UUID(i) for i in with_files],
                system,
                value,
                price_types=read_types,
            ):
                if mode != "plan" and p.price_type == "negotiated":
                    has_plan_rates.add(p.facility_id)
                    continue
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
            exact = [
                p
                for p in rows
                if p.price_type == "negotiated" and matches(p, spellings, st.get(p.facility_id, ""))
            ]
            pool = exact or [
                p
                for p in rows
                if p.price_type == "negotiated" and matches(p, fallback, st.get(p.facility_id, ""))
            ]
            if pool and not exact:
                uses_all_plans.add(fid)
            filtered[fid] = [p for p in rows if p.price_type != "negotiated"] + pool
        by_facility = filtered
    if payer_id is not None:
        by_facility = {
            fid: [
                p
                for p in rows
                if p.price_type != "negotiated" or matches(p, spellings, st.get(p.facility_id, ""))
            ]
            for fid, rows in by_facility.items()
        }
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
    # a place that published the service's own code is priced by it; a place
    # that published only another system's code for the same stay is priced
    # by that, and labeled (D-066)
    by_facility, priced_as = prefer_own_codes(by_facility, variants)
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
        if payer_id is not None:
            rows = [
                p
                for p in rows
                if p.price_type != "negotiated" or matches(p, spellings, st.get(p.facility_id, ""))
            ]
        if plan_id is not None:
            wanted = fallback if fid in uses_all_plans else spellings
            rows = [
                p
                for p in rows
                if p.price_type != "negotiated" or matches(p, wanted, st.get(p.facility_id, ""))
            ]
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
            plan_rates_only=(
                mode != "plan" and not by_facility.get(str(f[0])) and str(f[0]) in has_plan_rates
            ),
            doctor_fee=doctor_fee(
                by_facility.get(str(f[0]), ()),
                "cash" if str(f[0]) in cash_instead else mode,
            ),
            change_percent=change(str(f[0])),
            all_plans_rate=str(f[0]) in uses_all_plans,
            special=specials.get(str(f[0])),
            delivery=delivery.get(str(f[0])),
            priced_as=priced_as.get(str(f[0]), ()),
            reason=_reason(bool(by_facility.get(str(f[0]))), published.get(str(f[0])), f[7], f[6]),
            psychiatric=f[6] == "psychiatric_hospital",
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
        all_plans_spellings=fallback,
        code_description=code_description,
        code_name=_code_name(conn, codes[0]) if service_slug is None and codes else None,
        insurer_unsure=insurer_name,
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
    if kinds:
        # (2026-11-23: the free-care check took 7 seconds near Las Vegas) start
        # from the few places of the chosen kinds (hospitals: a few thousand
        # nationwide) instead of walking the map index past every nearby
        # office until enough hospitals turn up
        cand = """
                SELECT f.id FROM ref.facility_provider_type x
                JOIN ref.facility f ON f.id = x.facility_id, p
                WHERE x.provider_type = ANY(CAST(:kinds AS text[]))
                  AND f.geom IS NOT NULL AND f.status = 'active'
                  AND ST_DWithin(f.geom, p.pt, :meters)
                GROUP BY f.id, f.geom, p.pt
                ORDER BY ST_Distance(f.geom, p.pt)
                LIMIT :n
        """
    else:
        cand = """  -- nearest first, straight from the map index (2026-11-12)
                SELECT f.id FROM ref.facility f, p
                WHERE f.geom IS NOT NULL AND f.status = 'active'
                   AND ST_DWithin(f.geom, p.pt, :meters)
                ORDER BY f.geom <-> p.pt
                LIMIT :n
        """
    rows = conn.execute(
        text(
            """
            WITH p AS (
                SELECT CAST(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS geography) AS pt
            ),
            cand AS ({cand})
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
            """.replace("{cand}", cand)
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
    # a short plain explanation of the service (Cooper, 2026-11-12); for a code,
    # the hospitals' own wording when the name shown is ours
    about: str | None = None


def suggest(conn: Connection, query: str, limit: int = 10) -> list[Suggestion]:
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
            SELECT p.slug, p.consumer_name, p.unit, m.matched, min(m.rank) AS r, p.includes
            FROM ref.procedure p
            JOIN (
                SELECT id AS pid, consumer_name AS matched,
                       CASE WHEN lower(consumer_name) = :q THEN -1
                            WHEN lower(consumer_name) LIKE :prefix THEN 0 ELSE 1 END AS rank
                FROM ref.procedure WHERE lower(consumer_name) LIKE :like
                UNION ALL
                SELECT procedure_id, term,
                       -- an exact everyday word ("birth") beats a longer one that
                       -- starts the same way ("birth control coil")
                       CASE WHEN term_normalized = :q THEN -1
                            WHEN term_normalized LIKE :prefix THEN 0 ELSE 2 END
                FROM ref.procedure_synonym
                WHERE review_state = 'approved' AND term_normalized LIKE :like
            ) m ON m.pid = p.id
            WHERE p.review_state = 'approved' AND p.slug IS NOT NULL AND p.kind = 'service'
            GROUP BY p.slug, p.consumer_name, p.unit, m.matched, p.includes
            ORDER BY r, length(m.matched), p.consumer_name
            LIMIT :n
            """
        ),
        {"like": like, "prefix": q + "%", "q": q, "n": max(1, min(limit, 20))},
    ).all()
    seen: set[str] = set()
    out = []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(str(r[0]))
        out.append(Suggestion(str(r[0]), str(r[1]), str(r[2]), str(r[3]), about=r[5]))
    room = max(0, max(1, min(limit, 20)) - len(out))
    if room:
        # codes come after services (Cooper, 2026-11-12), and a code that belongs
        # to a service already suggested isn't listed again
        for c in _code_suggestions(conn, query.strip(), q, room + len(out)):
            # two codes of one service (99386 and 99396) list the service once
            if c.slug not in seen:
                seen.add(c.slug)
                out.append(c)
        out = out[: max(1, min(limit, 20))]
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
        # by words: the same finder as the "all options" list, widened words
        # included ("birth" finds deliveries, C-sections, newborn care), each
        # hospital's own item codes left to that list
        from .code_search import find_options

        found = [o for o in find_options(conn, raw, limit=200) if o.group != "hospital_item"]
        # the searched thing's own codes first, then most widely published
        found.sort(key=lambda o: (not o.core, -o.places, -o.prices))
        picks: list[Suggestion] = []
        for o in found[:n]:
            if o.service_slug:
                picks.append(
                    Suggestion(
                        o.service_slug,
                        o.name,
                        o.service_unit or "per_service",
                        f"{o.code_system} {o.code}",
                    )
                )
                continue
            picks.append(
                Suggestion(
                    slug=f"code:{o.code_system}:{o.code}",
                    name=o.name,
                    unit="per_service",
                    matched=f"{o.code_system} {o.code}",
                    kind="code",
                    code_system=o.code_system,
                    code=o.code,
                    about=o.wording,
                )
            )
        return picks
    else:
        return []
    if not rows:
        return []
    from .code_names import drg_plain

    pairs = [f"{r[0]}:{r[1]}" for r in rows]
    # a code that belongs to an approved service: suggest the service instead
    services = {
        str(x[0]): (str(x[1]), str(x[2]), str(x[3]), x[4])
        for x in conn.execute(
            text(
                """
                SELECT DISTINCT ON (pc.code_system::text || ':' || pc.code)
                       pc.code_system::text || ':' || pc.code, p.slug, p.consumer_name, p.unit,
                       p.includes
                FROM ref.procedure_code pc JOIN ref.procedure p ON p.id = pc.procedure_id
                WHERE pc.review_state = 'approved' AND p.review_state = 'approved'
                  AND p.kind = 'service'
                  AND p.slug IS NOT NULL
                  AND pc.code_system::text || ':' || pc.code = ANY(:pairs)
                ORDER BY pc.code_system::text || ':' || pc.code, p.consumer_name
                """
            ),
            {"pairs": pairs},
        ).all()
    }
    titles = {
        str(x[0]): str(x[1])
        for x in conn.execute(
            text(
                """
                SELECT DISTINCT ON (code) code, descriptor FROM ref.code
                WHERE system = 'MS-DRG' AND descriptor IS NOT NULL AND code = ANY(:codes)
                ORDER BY code, version DESC
                """
            ),
            {"codes": [str(r[1]) for r in rows if str(r[0]) == "MS-DRG"]},
        ).all()
    }
    out: list[Suggestion] = []
    for r in rows:
        key = f"{r[0]}:{r[1]}"
        if key in services:
            slug, name, unit, about = services[key]
            out.append(Suggestion(slug, name, unit, f"{r[0]} {r[1]}", about=about))
            continue
        wording = str(r[2] or f"{r[0]} {r[1]}")
        plain = drg_plain(titles[str(r[1])]) if str(r[1]) in titles else None
        out.append(
            Suggestion(
                slug=f"code:{r[0]}:{r[1]}",
                name=plain or wording,
                unit="per_service",
                matched=f"{r[0]} {r[1]}",
                kind="code",
                code_system=str(r[0]),
                code=str(r[1]),
                about=wording if plain else None,
            )
        )
    return out


def payer_suggestions(
    conn: Connection, query: str, limit: int = 10, facility_ids: list[str] | None = None
) -> list[tuple[str, int]]:
    """Insurer names exactly as hospitals wrote them (raw text, number of places).
    With facility_ids (places near the person), only names those places
    published, leaving out names already matched to an insurer on the card list
    (Cooper, 2026-11-12: "Blue Cross" listed insurers from every state)."""
    from .matching import normalize_name

    q = normalize_name(query)
    if len(q) < 2 or len(q) > 60:
        return []
    n = max(1, min(limit, 20))
    if facility_ids is not None:
        if not facility_ids:
            return []
        rows = conn.execute(
            text(
                "SELECT payer_name_raw, count(DISTINCT facility_id) FROM price.published_payer "
                "WHERE facility_id = ANY(CAST(:ids AS uuid[])) GROUP BY payer_name_raw"
            ),
            {"ids": facility_ids},
        ).all()
        matched = {
            str(r[0])
            for r in conn.execute(
                text(
                    "SELECT DISTINCT raw_payer_normalized FROM ref.plan_alias "
                    "WHERE review_state = 'approved'"
                )
            ).all()
        }
        counts: dict[str, tuple[str, int]] = {}
        for raw, places in rows:
            key = normalize_name(str(raw))
            if q not in key or key in matched:
                continue
            name, total = counts.get(key, (str(raw), 0))
            counts[key] = (name, total + int(places))
        best = sorted(counts.values(), key=lambda v: (-v[1], v[0]))
        return best[:n]
    rows = conn.execute(
        text(
            "SELECT raw_text, facilities FROM ref.payer_index WHERE raw_normalized LIKE :p "
            "ORDER BY facilities DESC, prices DESC LIMIT :n"
        ),
        {"p": "%" + q.replace("%", "").replace("_", "") + "%", "n": n},
    ).all()
    return [(str(r[0]), int(r[1])) for r in rows]
