"""Service catalog and provider types (D-032).

Both come from committed CSV files with review columns:
- data/reference/provider_types.csv
- data/reference/service_catalog.csv (codes as "SYSTEM:code@version|...")

Rows without a reviewer are loaded as 'proposed' (visible on the review page,
never used by search); rows with a reviewer and date are 'approved'. Code
links are created only to code numbers: a missing ref.code row is added with
no descriptor (CPT and CDT descriptors are never loaded, D-002/Q16).

Facilities get provider types from their CMS facility type automatically
(source 'cms_facility_type'); providers and reviewers add others later.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import Connection, text

from procedurescout_core.enums import CodeSystem

from .common import LoadStats, read_delimited, require_columns

PROVIDER_TYPE_COLUMNS = ("code", "name", "source", "reviewed_by", "reviewed_at")
SERVICE_COLUMNS = (
    "slug",
    "name",
    "category",
    "unit",
    "codes",
    "source",
    "reviewed_by",
    "reviewed_at",
    "notes",
)
CMS_TYPE_TO_PROVIDER_TYPE = {
    "acute_care_hospital": "hospital",
    "critical_access_hospital": "hospital",
    "childrens_hospital": "hospital",
    "psychiatric_hospital": "hospital",
    "rehabilitation_hospital": "hospital",
    "long_term_care_hospital": "hospital",
    "ambulatory_surgery_center": "surgery_center",
}
_CODE_REF = re.compile(r"^([A-Z][A-Z-]*):([A-Za-z0-9.\-]+)@([A-Za-z0-9.\-]+)$")
SOURCES = ("human", "ai_suggested", "import")


def _review(row: dict[str, str], ref: str, stats: LoadStats) -> tuple[str, str | None, date | None]:
    who = row["reviewed_by"].strip()
    when = row["reviewed_at"].strip()
    if not who and not when:
        return "proposed", None, None
    if not who or not when:
        stats.reject(ref, "half_reviewed", "reviewed_by and reviewed_at go together")
        return "proposed", None, None
    return "approved", who, date.fromisoformat(when)


def load_provider_types(conn: Connection, csv_text: str) -> LoadStats:
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    require_columns(rows, PROVIDER_TYPE_COLUMNS, "provider types CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i}"
        if row["source"] not in SOURCES:
            stats.reject(ref, "source", f"unknown source {row['source']!r}")
            continue
        state, who, when = _review(row, ref, stats)
        conn.execute(
            text(
                """
                INSERT INTO ref.provider_type (code, name, source, review_state, reviewed_by,
                                               reviewed_at, grouping, referral)
                VALUES (:c, :n, CAST(:s AS ref.suggestion_source),
                        CAST(:st AS ref.review_state), :rb, CAST(:ra AS timestamptz), :g, :rf)
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, source = EXCLUDED.source,
                    review_state = EXCLUDED.review_state, reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = EXCLUDED.reviewed_at, grouping = EXCLUDED.grouping,
                    referral = EXCLUDED.referral
                """
            ),
            {
                "c": row["code"].strip(),
                "n": row["name"].strip(),
                "s": row["source"],
                "st": state,
                "rb": who,
                "ra": when,
                "g": (row.get("grouping") or "").strip() or None,
                "rf": (row.get("referral") or "").strip() or None,
            },
        )
        stats.rows_loaded += 1
        stats.count(state)
    return stats


def assign_cms_provider_types(conn: Connection) -> int:
    """Hospital / surgery-center types from CMS facility types (approved types only)."""
    total = 0
    for cms_type, ptype in CMS_TYPE_TO_PROVIDER_TYPE.items():
        result = conn.execute(
            text(
                """
                INSERT INTO ref.facility_provider_type (facility_id, provider_type, source)
                SELECT f.id, pt.code, 'cms_facility_type'
                FROM ref.facility f JOIN ref.provider_type pt ON pt.code = :p
                WHERE f.facility_type = CAST(:t AS ref.facility_type)
                  AND pt.review_state = 'approved'
                ON CONFLICT DO NOTHING
                """
            ),
            {"p": ptype, "t": cms_type},
        )
        total += result.rowcount or 0
    return total


def load_services(conn: Connection, csv_text: str) -> LoadStats:
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    require_columns(rows, SERVICE_COLUMNS, "service catalog CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i} {row['slug']}"
        if row["source"] not in SOURCES:
            stats.reject(ref, "source", f"unknown source {row['source']!r}")
            continue
        codes: list[tuple[str, str, str]] = []
        bad = False
        for part in filter(None, (p.strip() for p in row["codes"].split("|"))):
            m = _CODE_REF.match(part)
            if not m or m.group(1) not in {c.value for c in CodeSystem}:
                stats.reject(ref, "code", f"not SYSTEM:code@version: {part!r}")
                bad = True
                break
            codes.append((m.group(1), m.group(2), m.group(3)))
        if bad:
            continue
        state, who, when = _review(row, ref, stats)
        savepoint = conn.begin_nested()
        try:
            pid = conn.execute(
                text(
                    """
                    INSERT INTO ref.procedure (consumer_name, category, description_plain, slug,
                        unit, source, review_state, reviewed_by, reviewed_at, includes)
                    VALUES (:n, :c, :d, :slug, :u, CAST(:s AS ref.suggestion_source),
                            CAST(:st AS ref.review_state), :rb, CAST(:ra AS timestamptz), :inc)
                    ON CONFLICT (slug) DO UPDATE SET consumer_name = EXCLUDED.consumer_name,
                        category = EXCLUDED.category,
                        description_plain = EXCLUDED.description_plain,
                        includes = EXCLUDED.includes,
                        unit = EXCLUDED.unit, source = EXCLUDED.source,
                        review_state = EXCLUDED.review_state, reviewed_by = EXCLUDED.reviewed_by,
                        reviewed_at = EXCLUDED.reviewed_at
                    RETURNING id
                    """
                ),
                {
                    "n": row["name"].strip(),
                    "c": row["category"].strip() or None,
                    "d": row["notes"].strip() or None,
                    "slug": row["slug"].strip(),
                    "u": row["unit"].strip(),
                    "s": row["source"],
                    "st": state,
                    "rb": who,
                    "ra": when,
                    "inc": (row.get("includes") or "").strip() or None,
                },
            ).scalar_one()
            # which kinds of provider offer it (optional column; codes from provider_types.csv)
            types = [t for t in (row.get("provider_types") or "").split("|") if t.strip()]
            conn.execute(
                text("DELETE FROM ref.procedure_provider_type WHERE procedure_id = :p"), {"p": pid}
            )
            for ptype in types:
                conn.execute(
                    text(
                        "INSERT INTO ref.procedure_provider_type (procedure_id, provider_type) "
                        "VALUES (:p, :t)"
                    ),
                    {"p": pid, "t": ptype.strip()},
                )
            for system, code, version in codes:
                conn.execute(
                    text(
                        "INSERT INTO ref.code (system, code, version) "
                        "VALUES (CAST(:s AS ref.code_system), :c, :v) ON CONFLICT DO NOTHING"
                    ),
                    {"s": system, "c": code, "v": version},
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO ref.procedure_code (procedure_id, code_system, code,
                            code_version, role, review_state, reviewed_by, reviewed_at)
                        VALUES (:p, CAST(:s AS ref.code_system), :c, :v, 'primary',
                                CAST(:st AS ref.review_state), :rb, CAST(:ra AS timestamptz))
                        ON CONFLICT (procedure_id, code_system, code, code_version)
                        DO UPDATE SET review_state = EXCLUDED.review_state,
                            reviewed_by = EXCLUDED.reviewed_by, reviewed_at = EXCLUDED.reviewed_at
                        """
                    ),
                    {
                        "p": pid,
                        "s": system,
                        "c": code,
                        "v": version,
                        "st": state,
                        "rb": who,
                        "ra": when,
                    },
                )
        except Exception as exc:  # a bad row is reported, the rest still load
            savepoint.rollback()
            stats.reject(ref, "refused_by_database", str(exc).splitlines()[0][:300])
            continue
        savepoint.commit()
        stats.rows_loaded += 1
        stats.count(state)
    return stats


# ------------------------------------------------------------------ bundles
BUNDLE_COLUMNS = (
    "bundle_slug",
    "bundle_name",
    "category",
    "setting",
    "position",
    "label",
    "role",
    "requirement",
    "included_by_default",
    "code",
    "notes",
    "source",
    "reviewed_by",
    "reviewed_at",
)


def load_bundles(conn: Connection, csv_text: str) -> LoadStats:
    """Bundles (kind 'bundle' in ref.procedure) and their components. A bundle
    is approved only when every one of its components is approved."""
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, BUNDLE_COLUMNS, "bundles CSV")
    by_bundle: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for i, row in enumerate(rows, start=2):
        by_bundle.setdefault(row["bundle_slug"].strip(), []).append((i, row))
    for slug, items in by_bundle.items():
        first = items[0][1]
        states = []
        for i, row in items:
            states.append(_review(row, f"line:{i}", stats))
        all_approved = all(s[0] == "approved" for s in states)
        who = states[0][1] if all_approved else None
        when = states[0][2] if all_approved else None
        savepoint = conn.begin_nested()
        try:
            bid = conn.execute(
                text(
                    """
                    INSERT INTO ref.procedure (consumer_name, category, setting, slug, unit, kind,
                        source, review_state, reviewed_by, reviewed_at)
                    VALUES (:n, :c, CAST(:set AS ref.service_setting), :slug, 'per_service',
                            'bundle', CAST(:src AS ref.suggestion_source),
                            CAST(:st AS ref.review_state), :rb, CAST(:ra AS timestamptz))
                    ON CONFLICT (slug) DO UPDATE SET consumer_name = EXCLUDED.consumer_name,
                        category = EXCLUDED.category, setting = EXCLUDED.setting, kind = 'bundle',
                        source = EXCLUDED.source, review_state = EXCLUDED.review_state,
                        reviewed_by = EXCLUDED.reviewed_by, reviewed_at = EXCLUDED.reviewed_at
                    RETURNING id
                    """
                ),
                {
                    "n": first["bundle_name"].strip(),
                    "c": first["category"].strip() or None,
                    "set": first["setting"].strip() or None,
                    "slug": slug,
                    "src": first["source"],
                    "st": "approved" if all_approved else "proposed",
                    "rb": who,
                    "ra": when,
                },
            ).scalar_one()
            conn.execute(text("DELETE FROM ref.bundle_component WHERE bundle_id = :b"), {"b": bid})
            for (i, row), (state, rb, ra) in zip(items, states, strict=True):
                m = _CODE_REF.match(row["code"].strip())
                if not m:
                    raise ValueError(f"line {i}: not SYSTEM:code@version: {row['code']!r}")
                conn.execute(
                    text(
                        "INSERT INTO ref.code (system, code, version) "
                        "VALUES (CAST(:s AS ref.code_system), :c, :v) ON CONFLICT DO NOTHING"
                    ),
                    {"s": m.group(1), "c": m.group(2), "v": m.group(3)},
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO ref.bundle_component (bundle_id, position, label, role,
                            requirement, included_by_default, code_system, code, code_version,
                            notes, source, review_state, reviewed_by, reviewed_at)
                        VALUES (:b, :pos, :label, :role, :req, :dflt,
                                CAST(:s AS ref.code_system), :c, :v, :notes,
                                CAST(:src AS ref.suggestion_source), CAST(:st AS ref.review_state),
                                :rb, CAST(:ra AS timestamptz))
                        """
                    ),
                    {
                        "b": bid,
                        "pos": int(row["position"]),
                        "label": row["label"].strip(),
                        "role": row["role"].strip(),
                        "req": row["requirement"].strip(),
                        "dflt": row["included_by_default"].strip().lower() == "true",
                        "s": m.group(1),
                        "c": m.group(2),
                        "v": m.group(3),
                        "notes": row["notes"].strip() or None,
                        "src": row["source"],
                        "st": state,
                        "rb": rb,
                        "ra": ra,
                    },
                )
        except Exception as exc:  # one bad bundle is reported; the others still load
            savepoint.rollback()
            stats.reject(slug, "bundle_refused", str(exc).splitlines()[0][:300])
            continue
        savepoint.commit()
        stats.rows_in += len(items)
        stats.rows_loaded += len(items)
        stats.count("bundles_approved" if all_approved else "bundles_proposed")
    return stats


# ------------------------------------------------------------------ assistance
GUIDELINE_COLUMNS = ("year", "region", "household_size", "amount", "per_additional", "source_url")
POLICY_COLUMNS = (
    "ccn",
    "policy_url",
    "application_url",
    "summary_url",
    "phone",
    "guideline_year",
    "effective_date",
    "checked_at",
    "evidence",
    "tiers",
    "notes",
    "source",
    "reviewed_by",
    "reviewed_at",
)
_TIER = re.compile(r"^(free|discount)<=(\d+(?:\.\d+)?)(?::(.+))?$")


def load_poverty_guidelines(conn: Connection, csv_text: str) -> LoadStats:
    from decimal import Decimal

    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    require_columns(rows, GUIDELINE_COLUMNS, "poverty guidelines CSV")
    for row in rows:
        stats.rows_in += 1
        conn.execute(
            text(
                """
                INSERT INTO ref.poverty_guideline (year, region, household_size, amount,
                    per_additional, source_url)
                VALUES (:y, :r, :h, :a, :p, :u)
                ON CONFLICT (year, region, household_size) DO UPDATE SET amount = EXCLUDED.amount,
                    per_additional = EXCLUDED.per_additional, source_url = EXCLUDED.source_url
                """
            ),
            {
                "y": int(row["year"]),
                "r": row["region"],
                "h": int(row["household_size"]),
                "a": Decimal(row["amount"]),
                "p": Decimal(row["per_additional"]),
                "u": row["source_url"],
            },
        )
        stats.rows_loaded += 1
    return stats


def load_assistance_policies(conn: Connection, csv_text: str) -> LoadStats:
    """Hospitals' financial assistance policies, entered by a person from the
    hospital's own policy document. tiers: "free<=200;discount<=400:50" (50%
    off) or "discount<=300:sliding scale"."""
    from decimal import Decimal

    from procedurescout_core.facility_repo import resolve_facility_by_ccn

    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, POLICY_COLUMNS, "assistance policies CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i} ccn:{row['ccn']}"
        fid = resolve_facility_by_ccn(conn, row["ccn"])
        if fid is None:
            stats.reject(ref, "facility_not_found", "CCN not loaded")
            continue
        tiers: list[tuple[str, Decimal, Decimal | None, str | None]] = []
        for part in filter(None, (p.strip() for p in row["tiers"].split(";"))):
            m = _TIER.match(part)
            if not m:
                stats.reject(ref, "tier", f"not free<=N or discount<=N:detail: {part!r}")
                tiers = []
                break
            detail = m.group(3)
            pct = Decimal(detail) if detail and re.fullmatch(r"\d+(\.\d+)?", detail) else None
            desc = None if pct is not None else detail
            tiers.append((m.group(1), Decimal(m.group(2)), pct, desc))
        if not tiers:
            stats.reject(ref, "no_tiers", "a policy needs at least one income limit")
            continue
        state, who, when = _review(row, ref, stats)
        conn.execute(
            text("DELETE FROM ref.assistance_policy WHERE facility_id = :f AND policy_url = :u"),
            {"f": fid, "u": row["policy_url"]},
        )
        pid = conn.execute(
            text(
                """
                INSERT INTO ref.assistance_policy (facility_id, policy_url, application_url,
                    summary_url, phone, guideline_year, effective_date, checked_at, evidence,
                    notes, source, review_state, reviewed_by, reviewed_at)
                VALUES (:f, :pu, :au, :su, :ph, :gy, CAST(:ed AS date), CAST(:ca AS date), :ev,
                        :no, CAST(:src AS ref.suggestion_source), CAST(:st AS ref.review_state),
                        :rb, CAST(:ra AS timestamptz))
                RETURNING id
                """
            ),
            {
                "f": fid,
                "pu": row["policy_url"],
                "au": row["application_url"] or None,
                "su": row["summary_url"] or None,
                "ph": row["phone"] or None,
                "gy": int(row["guideline_year"]) if row["guideline_year"] else None,
                "ed": row["effective_date"] or None,
                "ca": row["checked_at"],
                "ev": row["evidence"],
                "no": row["notes"] or None,
                "src": row["source"],
                "st": state,
                "rb": who,
                "ra": when,
            },
        ).scalar_one()
        for benefit, limit, pct, desc in tiers:
            conn.execute(
                text(
                    "INSERT INTO ref.assistance_tier (policy_id, max_percent_fpg, benefit, "
                    "discount_percent, description) VALUES (:p, :m, :b, :d, :ds)"
                ),
                {"p": pid, "m": limit, "b": benefit, "d": pct, "ds": desc},
            )
        stats.rows_loaded += 1
        stats.count(state)
    return stats


# ------------------------------------------------------------------ payers and plans
PAYER_COLUMNS = ("payer", "plan", "product_type", "segment", "reviewed_by", "reviewed_at")
ALIAS_COLUMNS = ("raw_payer", "raw_plan", "payer", "plan", "reviewed_by", "reviewed_at", "notes")


def load_payers(conn: Connection, csv_text: str) -> LoadStats:
    """Insurers and plans by the names on people's cards (data/reference/payers.csv)."""
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, PAYER_COLUMNS, "payers CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        if not row["reviewed_by"] or not row["reviewed_at"]:
            stats.count("unreviewed")
            continue
        pid = conn.execute(
            text(
                "INSERT INTO ref.payer (canonical_name) VALUES (:n) "
                "ON CONFLICT (canonical_name) "
                "DO UPDATE SET canonical_name = EXCLUDED.canonical_name "
                "RETURNING id"
            ),
            {"n": row["payer"].strip()},
        ).scalar_one()
        try:
            conn.execute(
                text(
                    """
                    INSERT INTO ref.plan (payer_id, canonical_name, product_type, segment)
                    VALUES (:p, :n, CAST(:pt AS ref.product_type), CAST(:sg AS ref.plan_segment))
                    ON CONFLICT (payer_id, canonical_name) DO UPDATE SET
                        product_type = EXCLUDED.product_type, segment = EXCLUDED.segment
                    """
                ),
                {
                    "p": pid,
                    "n": row["plan"].strip(),
                    "pt": row["product_type"].strip() or "unknown",
                    "sg": row["segment"].strip() or "unknown",
                },
            )
        except Exception as exc:  # bad enum value: report the line
            raise ValueError(f"payers.csv line {i}: {exc}") from exc
        stats.rows_loaded += 1
    return stats


def load_payer_aliases(conn: Connection, csv_text: str) -> LoadStats:
    """Reviewed links from a hospital file's exact payer + plan spelling to a plan
    on people's cards. Only rows with a reviewer are approved; the rest wait."""
    from procedurescout_core.matching import normalize_name

    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, ALIAS_COLUMNS, "payer aliases CSV")
    payer_of: dict[str, object] = {}
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i}"
        state, who, when = _review(row, ref, stats)
        plan = conn.execute(
            text(
                "SELECT pl.id, py.id FROM ref.plan pl JOIN ref.payer py ON py.id = pl.payer_id "
                "WHERE py.canonical_name = :py AND pl.canonical_name = :pl"
            ),
            {"py": row["payer"].strip(), "pl": row["plan"].strip()},
        ).first()
        if plan is None:
            stats.reject(ref, "plan_not_found", f"{row['payer']} / {row['plan']} not in payers.csv")
            continue
        raw_payer, raw_plan = row["raw_payer"], row["raw_plan"]
        # one hospital payer spelling can hold plans of several companies (e.g.
        # "Sierra Health and Life" | "HPN Medicaid"); matching uses the plan
        # alias below, so the payer alias keeps the first company and says so
        payer_key = normalize_name(raw_payer)
        if payer_of.setdefault(payer_key, plan[1]) != plan[1]:
            stats.count("payer_spelling_shared")
        else:
            _payer_alias(conn, raw_payer, payer_key, plan[1], state, who, when)
        conn.execute(
            text(
                """
                INSERT INTO ref.plan_alias (raw_payer_normalized, raw_plan_text,
                    raw_plan_normalized, plan_id, match_type, review_state, reviewed_by,
                    reviewed_at)
                VALUES (:rp, :t, :k, :pl, 'manual', CAST(:st AS ref.review_state), :rb,
                        CAST(:ra AS timestamptz))
                ON CONFLICT (raw_payer_normalized, raw_plan_normalized) DO UPDATE SET
                    plan_id = EXCLUDED.plan_id, match_type = 'manual',
                    review_state = EXCLUDED.review_state, reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = EXCLUDED.reviewed_at
                """
            ),
            {
                "rp": payer_key,
                "t": raw_plan,
                "k": normalize_name(raw_plan),
                "pl": plan[0],
                "st": state,
                "rb": who,
                "ra": when,
            },
        )
        stats.rows_loaded += 1
        stats.count(state)
    return stats


def _payer_alias(
    conn: Connection,
    raw_payer: str,
    key: str,
    payer_id: object,
    state: str,
    who: object,
    when: object,
) -> None:
    conn.execute(
        text(
            """
                INSERT INTO ref.payer_alias (raw_text, raw_normalized, payer_id, match_type,
                    review_state, reviewed_by, reviewed_at)
                VALUES (:r, :k, :p, 'manual', CAST(:st AS ref.review_state), :rb,
                        CAST(:ra AS timestamptz))
                ON CONFLICT (raw_normalized) DO UPDATE SET payer_id = EXCLUDED.payer_id,
                    match_type = 'manual', review_state = EXCLUDED.review_state,
                    reviewed_by = EXCLUDED.reviewed_by, reviewed_at = EXCLUDED.reviewed_at
                """
        ),
        {
            "r": raw_payer,
            "k": key,
            "p": payer_id,
            "st": state,
            "rb": who,
            "ra": when,
        },
    )


def collect_unmapped_plans(conn: Connection) -> int:
    """Put every payer/plan spelling in staged or published prices into the
    review queue as unmapped (existing rows are left alone)."""
    from procedurescout_core.matching import normalize_name

    pairs = conn.execute(
        text(
            "SELECT DISTINCT payer_name_raw, plan_name_raw FROM price.price "
            "WHERE payer_name_raw IS NOT NULL AND plan_name_raw IS NOT NULL"
        )
    ).all()
    added = 0
    for payer, plan in pairs:
        conn.execute(
            text(
                "INSERT INTO ref.payer_alias (raw_text, raw_normalized, match_type, review_state) "
                "VALUES (:r, :k, 'unmapped', 'proposed') ON CONFLICT (raw_normalized) DO NOTHING"
            ),
            {"r": payer, "k": normalize_name(payer)},
        )
        result = conn.execute(
            text(
                """
                INSERT INTO ref.plan_alias (raw_payer_normalized, raw_plan_text,
                    raw_plan_normalized, match_type, review_state)
                VALUES (:rp, :t, :k, 'unmapped', 'proposed')
                ON CONFLICT (raw_payer_normalized, raw_plan_normalized) DO NOTHING
                """
            ),
            {"rp": normalize_name(payer), "t": plan, "k": normalize_name(plan)},
        )
        added += result.rowcount or 0
    return added


SYNONYM_COLUMNS = ("slug", "term", "source", "reviewed_by", "reviewed_at")


def load_synonyms(conn: Connection, csv_text: str) -> LoadStats:
    """Everyday words and misspellings people type ("knee scope"), each tied to
    one service. Unreviewed rows stay proposed and are not used (rule 10)."""
    from procedurescout_core.matching import normalize_name

    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, SYNONYM_COLUMNS, "service synonyms CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i}"
        pid = conn.execute(
            text("SELECT id FROM ref.procedure WHERE slug = :s"), {"s": row["slug"].strip()}
        ).scalar()
        if pid is None:
            stats.reject(ref, "service_not_found", f"no service {row['slug']!r}")
            continue
        state, who, when = _review(row, ref, stats)
        conn.execute(
            text(
                """
                INSERT INTO ref.procedure_synonym (procedure_id, term, term_normalized, source,
                    review_state, reviewed_by, reviewed_at)
                VALUES (:p, :t, :k, CAST(:s AS ref.suggestion_source),
                        CAST(:st AS ref.review_state), :rb, CAST(:ra AS timestamptz))
                ON CONFLICT (procedure_id, term_normalized) DO UPDATE SET
                    review_state = EXCLUDED.review_state, reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = EXCLUDED.reviewed_at
                """
            ),
            {
                "p": pid,
                "t": row["term"].strip(),
                "k": normalize_name(row["term"]),
                "s": row["source"],
                "st": state,
                "rb": who,
                "ra": when,
            },
        )
        stats.rows_loaded += 1
        stats.count(state)
    return stats


COVERAGE_COLUMNS = (
    "state",
    "program",
    "group",
    "min_percent_fpg",
    "max_percent_fpg",
    "label",
    "apply_url",
    "source_url",
    "effective_from",
    "notes",
    "reviewed_by",
    "reviewed_at",
)


def load_coverage_limits(conn: Connection, csv_text: str) -> LoadStats:
    """Medicaid, CHIP and marketplace-savings income limits (percent of the
    poverty guideline) with their official sources; proposed until reviewed."""
    stats = LoadStats()
    rows = read_delimited(csv_text, ",")
    if not rows:
        return stats
    require_columns(rows, COVERAGE_COLUMNS, "coverage limits CSV")
    for i, row in enumerate(rows, start=2):
        stats.rows_in += 1
        ref = f"line:{i}"
        state, who, when = _review(row, ref, stats)
        savepoint = conn.begin_nested()
        try:
            conn.execute(
                text(
                    """
                    INSERT INTO ref.coverage_limit (state_code, program, group_code,
                        min_percent_fpg, max_percent_fpg, label, apply_url, source_url,
                        effective_from, notes, review_state, reviewed_by, reviewed_at)
                    VALUES (:s, :p, :g, CAST(:mn AS numeric), CAST(:mx AS numeric), :l, :a, :src,
                        CAST(:e AS date), :n, CAST(:st AS ref.review_state), :rb,
                        CAST(:ra AS timestamptz))
                    ON CONFLICT (state_code, program, group_code) DO UPDATE SET
                        min_percent_fpg = EXCLUDED.min_percent_fpg,
                        max_percent_fpg = EXCLUDED.max_percent_fpg, label = EXCLUDED.label,
                        apply_url = EXCLUDED.apply_url, source_url = EXCLUDED.source_url,
                        effective_from = EXCLUDED.effective_from, notes = EXCLUDED.notes,
                        review_state = EXCLUDED.review_state, reviewed_by = EXCLUDED.reviewed_by,
                        reviewed_at = EXCLUDED.reviewed_at
                    """
                ),
                {
                    "s": row["state"].strip().upper(),
                    "p": row["program"].strip(),
                    "g": row["group"].strip(),
                    "mn": row["min_percent_fpg"].strip() or "0",
                    "mx": row["max_percent_fpg"].strip(),
                    "l": row["label"].strip(),
                    "a": row["apply_url"].strip(),
                    "src": row["source_url"].strip(),
                    "e": row["effective_from"].strip(),
                    "n": row["notes"].strip() or None,
                    "st": state,
                    "rb": who,
                    "ra": when,
                },
            )
        except Exception as exc:
            savepoint.rollback()
            stats.reject(ref, "refused_by_database", str(exc).splitlines()[0][:300])
            continue
        savepoint.commit()
        stats.rows_loaded += 1
        stats.count(state)
    return stats
