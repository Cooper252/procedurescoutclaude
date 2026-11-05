"""Initial schema: reference, source/lineage, prices, fixtures.

Revision ID: 0001
Revises:
Create Date: 2026-11-04

Design notes (details in docs/DATABASE_DESIGN.md and docs/DECISIONS.md):
- Four schemas: ref (facilities, codes, payers), src (files, import runs,
  dataset versions, audit), price (published price rows), fixture (synthetic
  test data that the API role can never read).
- price.price is long format: one row per amount, typed by price_type, so a
  gross charge, a cash price and a negotiated rate can never share a column.
- Amount columns are nullable with no defaults: missing is NULL, never 0.
- The API role reads prices only through price.published_price, which
  filters to published dataset versions.
- Enum values and import transitions are written out here on purpose
  (migrations are frozen history); tests check they match the Python code.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, list[str]] = {
    "ref.facility_type": [
        "acute_care_hospital",
        "critical_access_hospital",
        "childrens_hospital",
        "psychiatric_hospital",
        "rehabilitation_hospital",
        "long_term_care_hospital",
        "ambulatory_surgery_center",
        "other",
    ],
    "ref.facility_status": ["active", "inactive", "closed"],
    # Exactly the code types allowed by the CMS v3.0 schema (code_information.type).
    "ref.code_system": [
        "CPT",
        "HCPCS",
        "ICD",
        "DRG",
        "MS-DRG",
        "R-DRG",
        "S-DRG",
        "APS-DRG",
        "AP-DRG",
        "APR-DRG",
        "TRIS-DRG",
        "APC",
        "NDC",
        "HIPPS",
        "LOCAL",
        "EAPG",
        "CDT",
        "RC",
        "CDM",
        "CMG",
        "MS-LTC-DRG",
    ],
    "ref.service_setting": ["inpatient", "outpatient", "both"],
    "ref.code_role": ["primary", "variant", "related"],
    "ref.review_state": ["proposed", "approved", "rejected"],
    "ref.suggestion_source": ["human", "ai_suggested", "import"],
    "ref.product_type": ["hmo", "ppo", "epo", "pos", "hdhp", "indemnity", "other", "unknown"],
    "ref.plan_segment": [
        "commercial",
        "exchange",
        "employer_self_funded",
        "union_trust",
        "medicare_advantage",
        "medicaid_managed_care",
        "tricare_va",
        "workers_comp",
        "other",
        "unknown",
    ],
    "ref.match_type": ["exact", "normalized", "manual", "unmapped"],
    "src.discovery_method": ["cms_hpt_txt", "site_crawl", "index_file", "manual"],
    "src.file_format": ["json", "csv_tall", "csv_wide", "zip", "unknown"],
    "src.validation_state": [
        "not_validated",
        "valid",
        "valid_with_warnings",
        "invalid",
        "unsupported_version",
    ],
    "src.import_state": [
        "discovered",
        "queued",
        "downloading",
        "downloaded",
        "validating",
        "parsing",
        "normalizing",
        "loading",
        "quality_review",
        "published",
        "failed",
        "stale",
        "retired",
    ],
    "src.severity": ["error", "warning", "info"],
    "src.dataset_status": ["staged", "published", "retired"],
    "price.billing_class": ["facility", "professional", "both"],
    "price.price_type": [
        "gross",
        "discounted_cash",
        "negotiated",
        "deidentified_min",
        "deidentified_max",
        "median_allowed",
        "p10_allowed",
        "p90_allowed",
        # v2.0/v2.2 files only: removed from the CMS schema in v3.0.
        "estimated_allowed",
    ],
    "price.methodology": [
        "case_rate",
        "fee_schedule",
        "percent_of_total_billed_charges",
        "per_diem",
        "other",
    ],
}

_WORKING = [
    "queued",
    "downloading",
    "downloaded",
    "validating",
    "parsing",
    "normalizing",
    "loading",
    "quality_review",
]
IMPORT_TRANSITIONS: list[tuple[str, str]] = [
    ("discovered", "queued"),
    ("queued", "downloading"),
    ("downloading", "downloaded"),
    ("downloaded", "validating"),
    ("downloaded", "retired"),
    ("validating", "parsing"),
    ("parsing", "normalizing"),
    ("normalizing", "loading"),
    ("loading", "quality_review"),
    ("quality_review", "published"),
    ("published", "stale"),
    ("published", "retired"),
    ("stale", "published"),
    ("stale", "retired"),
    ("failed", "queued"),
    ("failed", "retired"),
    *[(w, "failed") for w in _WORKING],
]


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    for schema in ("ref", "src", "price", "fixture"):
        op.execute(f"CREATE SCHEMA {schema}")

    for name, values in ENUMS.items():
        op.execute(f"CREATE TYPE {name} AS ENUM ({', '.join(_q(v) for v in values)})")

    # ------------------------------------------------------------------ ref
    op.execute("""
    CREATE TABLE ref.health_system (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        name        text NOT NULL UNIQUE,
        created_at  timestamptz NOT NULL DEFAULT now()
    )""")

    op.execute("""
    CREATE TABLE ref.facility (
        id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        ccn                 text UNIQUE CHECK (ccn ~ '^[0-9A-Z]{6}$'),
        name                text NOT NULL,
        facility_type       ref.facility_type NOT NULL,
        ownership           text,
        health_system_id    uuid REFERENCES ref.health_system(id) ON DELETE SET NULL,
        address_line1       text,
        city                text,
        state_code          char(2) NOT NULL CHECK (state_code ~ '^[A-Z]{2}$'),
        zip5                text CHECK (zip5 ~ '^[0-9]{5}$'),
        county_fips         text CHECK (county_fips ~ '^[0-9]{5}$'),
        geom                geography(Point, 4326),
        geocode_source      text,
        phone               text,
        website             text,
        er_services         boolean,
        cms_overall_rating  smallint CHECK (cms_overall_rating BETWEEN 1 AND 5),
        cms_rating_as_of    date,
        status              ref.facility_status NOT NULL DEFAULT 'active',
        match_confidence    numeric(4,3) CHECK (match_confidence BETWEEN 0 AND 1),
        source_dataset      text,
        source_updated_at   timestamptz,
        created_at          timestamptz NOT NULL DEFAULT now(),
        updated_at          timestamptz NOT NULL DEFAULT now(),
        CHECK (geom IS NULL OR geocode_source IS NOT NULL),
        CHECK (cms_overall_rating IS NULL OR cms_rating_as_of IS NOT NULL)
    )""")
    op.execute("CREATE INDEX facility_geom_gix ON ref.facility USING gist (geom)")
    op.execute("CREATE INDEX facility_state_idx ON ref.facility (state_code)")

    op.execute("""
    CREATE TABLE ref.facility_alias (
        facility_id uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        alias       text NOT NULL,
        source      text NOT NULL,
        PRIMARY KEY (facility_id, alias)
    )""")

    op.execute("""
    CREATE TABLE ref.facility_relationship (
        parent_facility_id  uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        child_facility_id   uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        relationship_type   text NOT NULL
            CHECK (relationship_type IN ('campus_of', 'same_license', 'merged_into')),
        source              text NOT NULL,
        PRIMARY KEY (parent_facility_id, child_facility_id, relationship_type),
        CHECK (parent_facility_id <> child_facility_id)
    )""")

    op.execute("""
    CREATE TABLE ref.facility_npi (
        facility_id   uuid NOT NULL REFERENCES ref.facility(id) ON DELETE CASCADE,
        npi           char(10) NOT NULL UNIQUE CHECK (npi ~ '^[0-9]{10}$'),
        taxonomy_code text,
        source        text NOT NULL,
        PRIMARY KEY (facility_id, npi)
    )""")

    # CPT descriptors are AMA-licensed. Without a license (decision 2026-11-04),
    # a CPT row may carry the code but no official descriptor text.
    op.execute("""
    CREATE TABLE ref.code (
        system              ref.code_system NOT NULL,
        code                text NOT NULL,
        version             text NOT NULL,
        descriptor          text,
        descriptor_source   text,
        descriptor_licensed boolean NOT NULL DEFAULT false,
        effective_from      date,
        effective_to        date,
        PRIMARY KEY (system, code, version),
        CHECK (system <> 'CPT' OR descriptor IS NULL OR descriptor_licensed),
        CHECK (descriptor IS NULL OR descriptor_source IS NOT NULL),
        CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
    )""")

    op.execute("""
    CREATE TABLE ref.procedure (
        id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        consumer_name     text NOT NULL UNIQUE,
        category          text,
        setting           ref.service_setting,
        description_plain text,
        created_at        timestamptz NOT NULL DEFAULT now()
    )""")

    op.execute("""
    CREATE TABLE ref.procedure_code (
        procedure_id  uuid NOT NULL REFERENCES ref.procedure(id) ON DELETE CASCADE,
        code_system   ref.code_system NOT NULL,
        code          text NOT NULL,
        code_version  text NOT NULL,
        role          ref.code_role NOT NULL,
        review_state  ref.review_state NOT NULL DEFAULT 'proposed',
        reviewed_by   text,
        reviewed_at   timestamptz,
        notes         text,
        PRIMARY KEY (procedure_id, code_system, code, code_version),
        FOREIGN KEY (code_system, code, code_version)
            REFERENCES ref.code(system, code, version) ON DELETE RESTRICT,
        CHECK (review_state <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")

    op.execute("""
    CREATE TABLE ref.procedure_synonym (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        procedure_id    uuid NOT NULL REFERENCES ref.procedure(id) ON DELETE CASCADE,
        term            text NOT NULL,
        term_normalized text NOT NULL,
        source          ref.suggestion_source NOT NULL,
        review_state    ref.review_state NOT NULL DEFAULT 'proposed',
        reviewed_by     text,
        reviewed_at     timestamptz,
        UNIQUE (procedure_id, term_normalized),
        CHECK (review_state <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")

    op.execute("""
    CREATE TABLE ref.payer (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        canonical_name  text NOT NULL UNIQUE,
        parent_org      text,
        naic_code       text,
        states          char(2)[] NOT NULL DEFAULT '{}',
        notes           text,
        created_at      timestamptz NOT NULL DEFAULT now()
    )""")

    op.execute("""
    CREATE TABLE ref.plan (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        payer_id        uuid NOT NULL REFERENCES ref.payer(id) ON DELETE RESTRICT,
        canonical_name  text NOT NULL,
        product_type    ref.product_type NOT NULL DEFAULT 'unknown',
        segment         ref.plan_segment NOT NULL DEFAULT 'unknown',
        created_at      timestamptz NOT NULL DEFAULT now(),
        UNIQUE (payer_id, canonical_name)
    )""")

    # ------------------------------------------------------------------ src
    op.execute("""
    CREATE TABLE src.transparency_source (
        id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id       uuid REFERENCES ref.facility(id) ON DELETE RESTRICT,
        url               text NOT NULL UNIQUE CHECK (url ~ '^https?://'),
        discovery_method  src.discovery_method NOT NULL,
        last_checked_at   timestamptz,
        active            boolean NOT NULL DEFAULT true,
        created_at        timestamptz NOT NULL DEFAULT now()
    )""")

    op.execute("""
    CREATE TABLE src.transparency_file (
        id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        source_id             uuid NOT NULL REFERENCES src.transparency_source(id) ON DELETE RESTRICT,
        sha256                char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        bytes                 bigint NOT NULL CHECK (bytes >= 0),
        http_status           smallint NOT NULL,
        downloaded_at         timestamptz NOT NULL DEFAULT now(),
        reported_last_updated date,
        schema_version        text,
        format                src.file_format NOT NULL DEFAULT 'unknown',
        object_store_key      text NOT NULL,
        attester_name         text,
        attestation_text      text,
        validation_state      src.validation_state NOT NULL DEFAULT 'not_validated',
        UNIQUE (source_id, sha256)
    )""")

    # One file can cover several campuses.
    op.execute("""
    CREATE TABLE src.file_facility (
        file_id     uuid NOT NULL REFERENCES src.transparency_file(id) ON DELETE CASCADE,
        facility_id uuid NOT NULL REFERENCES ref.facility(id) ON DELETE RESTRICT,
        PRIMARY KEY (file_id, facility_id)
    )""")

    op.execute("""
    CREATE TABLE src.import_run (
        id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        file_id           uuid NOT NULL REFERENCES src.transparency_file(id) ON DELETE RESTRICT,
        parser_version    text NOT NULL,
        state             src.import_state NOT NULL DEFAULT 'discovered',
        state_changed_at  timestamptz NOT NULL DEFAULT now(),
        started_at        timestamptz,
        finished_at       timestamptz,
        rows_in           bigint CHECK (rows_in >= 0),
        rows_out          bigint CHECK (rows_out >= 0),
        rows_rejected     bigint CHECK (rows_rejected >= 0),
        error_summary     text,
        checkpoint        jsonb,
        created_at        timestamptz NOT NULL DEFAULT now()
    )""")

    op.execute("""
    CREATE TABLE src.import_transition (
        from_state src.import_state NOT NULL,
        to_state   src.import_state NOT NULL,
        PRIMARY KEY (from_state, to_state)
    )""")
    values = ", ".join(
        f"({_q(a)}::src.import_state, {_q(b)}::src.import_state)" for a, b in IMPORT_TRANSITIONS
    )
    op.execute(f"INSERT INTO src.import_transition (from_state, to_state) VALUES {values}")

    op.execute("""
    CREATE TABLE src.import_run_event (
        id            bigserial PRIMARY KEY,
        import_run_id uuid NOT NULL REFERENCES src.import_run(id) ON DELETE CASCADE,
        from_state    src.import_state,
        to_state      src.import_state NOT NULL,
        at            timestamptz NOT NULL DEFAULT now()
    )""")

    op.execute("""
    CREATE FUNCTION src.enforce_import_transition() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'INSERT' THEN
            IF NEW.state <> 'discovered' THEN
                RAISE EXCEPTION 'import run must start in state discovered, got %', NEW.state
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END IF;
        IF NEW.state IS DISTINCT FROM OLD.state THEN
            IF NOT EXISTS (
                SELECT 1 FROM src.import_transition
                WHERE from_state = OLD.state AND to_state = NEW.state
            ) THEN
                RAISE EXCEPTION 'illegal import transition % -> %', OLD.state, NEW.state
                    USING ERRCODE = 'check_violation';
            END IF;
            NEW.state_changed_at := now();
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""
    CREATE TRIGGER import_run_transition
    BEFORE INSERT OR UPDATE OF state ON src.import_run
    FOR EACH ROW EXECUTE FUNCTION src.enforce_import_transition()""")

    # Log after the row exists (an AFTER trigger), so the event's foreign key holds.
    op.execute("""
    CREATE FUNCTION src.log_import_transition() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'INSERT' THEN
            INSERT INTO src.import_run_event (import_run_id, from_state, to_state)
                VALUES (NEW.id, NULL, NEW.state);
        ELSIF NEW.state IS DISTINCT FROM OLD.state THEN
            INSERT INTO src.import_run_event (import_run_id, from_state, to_state)
                VALUES (NEW.id, OLD.state, NEW.state);
        END IF;
        RETURN NULL;
    END $$""")
    op.execute("""
    CREATE TRIGGER import_run_log
    AFTER INSERT OR UPDATE OF state ON src.import_run
    FOR EACH ROW EXECUTE FUNCTION src.log_import_transition()""")

    op.execute("""
    CREATE TABLE src.validation_result (
        id            bigserial PRIMARY KEY,
        import_run_id uuid NOT NULL REFERENCES src.import_run(id) ON DELETE CASCADE,
        severity      src.severity NOT NULL,
        rule          text NOT NULL,
        row_ref       text,
        message       text NOT NULL,
        created_at    timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX validation_result_run_idx ON src.validation_result (import_run_id)")

    op.execute("""
    CREATE TABLE src.dataset_version (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id   uuid NOT NULL REFERENCES ref.facility(id) ON DELETE RESTRICT,
        import_run_id uuid NOT NULL UNIQUE REFERENCES src.import_run(id) ON DELETE RESTRICT,
        status        src.dataset_status NOT NULL DEFAULT 'staged',
        published_at  timestamptz,
        retired_at    timestamptz,
        created_at    timestamptz NOT NULL DEFAULT now(),
        CHECK (status <> 'published' OR published_at IS NOT NULL),
        CHECK (status <> 'retired' OR retired_at IS NOT NULL)
    )""")
    # At most one published dataset per facility at any moment.
    op.execute("""
    CREATE UNIQUE INDEX dataset_version_one_published
    ON src.dataset_version (facility_id) WHERE status = 'published'""")

    op.execute("""
    CREATE TABLE src.audit_event (
        id          bigserial PRIMARY KEY,
        actor       text NOT NULL,
        action      text NOT NULL,
        entity_type text NOT NULL,
        entity_id   text NOT NULL,
        before      jsonb,
        after       jsonb,
        at          timestamptz NOT NULL DEFAULT now()
    )""")

    # Payer/plan alias tables reference src.transparency_file, so they come after it.
    op.execute("""
    CREATE TABLE ref.payer_alias (
        id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        raw_text           text NOT NULL,
        raw_normalized     text NOT NULL UNIQUE,
        payer_id           uuid REFERENCES ref.payer(id) ON DELETE RESTRICT,
        match_type         ref.match_type NOT NULL DEFAULT 'unmapped',
        confidence         numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
        review_state       ref.review_state NOT NULL DEFAULT 'proposed',
        first_seen_file_id uuid REFERENCES src.transparency_file(id) ON DELETE SET NULL,
        reviewed_by        text,
        reviewed_at        timestamptz,
        CHECK ((match_type = 'unmapped') = (payer_id IS NULL)),
        CHECK (review_state <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")

    op.execute("""
    CREATE TABLE ref.plan_alias (
        id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        raw_payer_normalized text NOT NULL,
        raw_plan_text        text NOT NULL,
        raw_plan_normalized  text NOT NULL,
        plan_id              uuid REFERENCES ref.plan(id) ON DELETE RESTRICT,
        match_type           ref.match_type NOT NULL DEFAULT 'unmapped',
        confidence           numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
        review_state         ref.review_state NOT NULL DEFAULT 'proposed',
        first_seen_file_id   uuid REFERENCES src.transparency_file(id) ON DELETE SET NULL,
        reviewed_by          text,
        reviewed_at          timestamptz,
        UNIQUE (raw_payer_normalized, raw_plan_normalized),
        CHECK ((match_type = 'unmapped') = (plan_id IS NULL)),
        CHECK (review_state <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
    )""")

    # ---------------------------------------------------------------- price
    op.execute("""
    CREATE TABLE price.price (
        id                    uuid NOT NULL DEFAULT gen_random_uuid(),
        state_code            char(2) NOT NULL CHECK (state_code ~ '^[A-Z]{2}$'),
        dataset_version_id    uuid NOT NULL REFERENCES src.dataset_version(id) ON DELETE RESTRICT,
        facility_id           uuid NOT NULL REFERENCES ref.facility(id) ON DELETE RESTRICT,
        raw_row_ref           text NOT NULL,
        code_system           ref.code_system NOT NULL,
        code                  text NOT NULL,
        modifiers             text[] NOT NULL DEFAULT '{}',
        setting               ref.service_setting,
        billing_class         price.billing_class,
        description_raw       text,
        drug_unit             numeric(16,4) CHECK (drug_unit > 0),
        drug_unit_type        text CHECK (drug_unit_type IN ('GR', 'ML', 'ME', 'UN', 'F2', 'GM', 'EA')),
        CHECK ((drug_unit IS NULL) = (drug_unit_type IS NULL)),
        payer_name_raw        text,
        plan_name_raw         text,
        payer_id              uuid REFERENCES ref.payer(id) ON DELETE RESTRICT,
        plan_id               uuid REFERENCES ref.plan(id) ON DELETE RESTRICT,
        match_type            ref.match_type,
        price_type            price.price_type NOT NULL,
        amount                numeric(16,4) CHECK (amount >= 0),
        percentage            numeric(9,4) CHECK (percentage BETWEEN 0 AND 1000),
        algorithm             text,
        methodology           price.methodology,
        -- CMS publishes the count as text: "0", "1 through 10", or a whole number >= 11.
        allowed_count_raw     text CHECK (CASE
                                  WHEN allowed_count_raw IS NULL THEN true
                                  WHEN allowed_count_raw IN ('0', '1 through 10') THEN true
                                  WHEN allowed_count_raw ~ '^[1-9][0-9]+$'
                                      THEN allowed_count_raw::numeric >= 11
                                  ELSE false END),
        amount_derived        boolean NOT NULL DEFAULT false,
        derivation_rule       text,
        additional_notes_raw  text,
        quality_flags         text[] NOT NULL DEFAULT '{}',
        PRIMARY KEY (state_code, id),

        -- A row must carry something that was actually published.
        CONSTRAINT price_has_value
            CHECK (amount IS NOT NULL OR percentage IS NOT NULL OR algorithm IS NOT NULL),
        -- Payer-specific types need the raw payer and plan exactly as published.
        CONSTRAINT price_payer_required
            CHECK (price_type NOT IN ('negotiated', 'median_allowed', 'p10_allowed', 'p90_allowed',
                                    'estimated_allowed')
                   OR (payer_name_raw IS NOT NULL AND plan_name_raw IS NOT NULL)),
        -- Gross, cash and de-identified min/max are not payer-specific.
        CONSTRAINT price_payer_forbidden
            CHECK (price_type NOT IN ('gross', 'discounted_cash', 'deidentified_min', 'deidentified_max')
                   OR (payer_name_raw IS NULL AND plan_name_raw IS NULL
                       AND payer_id IS NULL AND plan_id IS NULL)),
        -- Percentages and algorithms exist only for negotiated rates.
        CONSTRAINT price_formula_only_negotiated
            CHECK (price_type = 'negotiated' OR (percentage IS NULL AND algorithm IS NULL)),
        CONSTRAINT price_negotiated_needs_methodology
            CHECK (price_type <> 'negotiated' OR methodology IS NOT NULL),
        -- A dollar amount we computed must say how, and from which published formula.
        CONSTRAINT price_derivation_documented
            CHECK (NOT amount_derived
                   OR (amount IS NOT NULL AND derivation_rule IS NOT NULL
                       AND (percentage IS NOT NULL OR algorithm IS NOT NULL))),
        CONSTRAINT price_allowed_count_scope
            CHECK (allowed_count_raw IS NULL
                   OR price_type IN ('median_allowed', 'p10_allowed', 'p90_allowed')),
        -- A canonical payer/plan link needs a recorded match type.
        CONSTRAINT price_mapping_labeled
            CHECK ((payer_id IS NULL AND plan_id IS NULL)
                   OR (match_type IS NOT NULL AND match_type <> 'unmapped')),
        CONSTRAINT price_plan_needs_payer
            CHECK (plan_id IS NULL OR payer_id IS NOT NULL)
    ) PARTITION BY LIST (state_code)""")
    op.execute("CREATE TABLE price.price_nv PARTITION OF price.price FOR VALUES IN ('NV')")
    op.execute("CREATE TABLE price.price_default PARTITION OF price.price DEFAULT")
    op.execute(
        "CREATE INDEX price_code_facility_idx ON price.price (code_system, code, facility_id)"
    )
    op.execute(
        "CREATE INDEX price_plan_code_idx ON price.price (plan_id, code_system, code) "
        "WHERE plan_id IS NOT NULL"
    )
    op.execute("CREATE INDEX price_dataset_idx ON price.price (dataset_version_id)")

    # The only way the API role can see prices: published datasets only.
    op.execute("""
    CREATE VIEW price.published_price AS
    SELECT p.*, dv.published_at
    FROM price.price p
    JOIN src.dataset_version dv ON dv.id = p.dataset_version_id
    WHERE dv.status = 'published'""")

    # -------------------------------------------------------------- fixture
    op.execute("""
    CREATE TABLE fixture.synthetic_price (
        LIKE price.price INCLUDING DEFAULTS INCLUDING CONSTRAINTS
    )""")
    op.execute(
        "COMMENT ON TABLE fixture.synthetic_price IS "
        "'Synthetic test data only. Never readable by the API role; never shown to users.'"
    )

    # --------------------------------------------------------------- grants
    op.execute("REVOKE ALL ON SCHEMA ref, src, price, fixture FROM PUBLIC")
    api_role = os.environ.get("PS_API_ROLE", "ps_api")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", api_role):
        raise ValueError(f"PS_API_ROLE is not a plain role name: {api_role!r}")
    op.execute(f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {_q(api_role)}) THEN
            EXECUTE 'GRANT USAGE ON SCHEMA ref, src, price TO {api_role}';
            EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA ref TO {api_role}';
            EXECUTE 'GRANT SELECT ON src.transparency_source, src.transparency_file,
                     src.file_facility, src.dataset_version TO {api_role}';
            EXECUTE 'GRANT SELECT ON price.published_price TO {api_role}';
        ELSE
            RAISE NOTICE 'role % not found; API grants skipped', {_q(api_role)};
        END IF;
    END $$""")


def downgrade() -> None:
    for schema in ("fixture", "price", "src", "ref"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
