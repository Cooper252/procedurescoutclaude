"""Command line for reference-data loads.

    python -m procedurescout_ingest.reference.cli <command> [options]

Every command records a row in src.reference_load (source, checksum, counts,
rejects). Data changes run in one transaction: a failed load changes nothing
except its own 'failed' lineage row. Run `nv-all` for the standard Nevada
sequence. Needs DATABASE_URL (owner role).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import Connection, Engine, create_engine, text

from .. import discovery
from . import ahrq, census, cms_pdc, codes, facilities, geocode, nppes, relationships, websites
from .common import (
    USER_AGENT,
    LoadStats,
    SourceBlob,
    SourceError,
    acquire,
    begin_load,
    decode_text,
    fail_load,
    finish_load,
    maybe_unzip,
    new_client,
)

# Default official locations, confirmed 2026-11-04 (docs/DATA_SOURCES.md).
GAZETTEER_2026_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/"
    "2026_Gaz_zcta_national.zip"
)
ZCTA_COUNTY_REL_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
    "tab20_zcta520_county20_natl.txt"
)
HCPCS_OCT_2026_URL = "https://www.cms.gov/files/zip/october-2026-alpha-numeric-hcpcs-file.zip"
MSDRG_FY2027_TABLE5_URL = "https://www.cms.gov/files/zip/fy2027-ipps-fr-table-5.zip"
RELATIONSHIPS_CSV = "data/reference/facility_relationships_reviewed.csv"
WEBSITES_CSV = "data/reference/facility_websites.csv"
ALIASES_CSV = "data/reference/facility_aliases_reviewed.csv"
CAPTURED_DIR = "data/reference/hpt_captured"
MANUAL_SOURCES_CSV = "data/reference/price_file_sources_reviewed.csv"
CO_LISTED_CSV = "data/reference/hpt_co_listed_locations_reviewed.csv"
PROVIDER_TYPES_CSV = "data/reference/provider_types.csv"
SERVICE_CATALOG_CSV = "data/reference/service_catalog.csv"
BUNDLES_CSV = "data/reference/bundles.csv"
POVERTY_CSV = "data/reference/poverty_guidelines.csv"
ASSISTANCE_CSV = "data/reference/assistance_policies.csv"
PAYERS_CSV = "data/reference/payers.csv"
PAYER_ALIASES_CSV = "data/reference/payer_aliases.csv"
SYNONYMS_CSV = "data/reference/service_synonyms.csv"
COVERAGE_CSV = "data/reference/coverage_limits.csv"
STEP_DATASETS = {
    "hospitals": "cms_hospital_general_information",
    "ascs": "cms_asc_facility",
    "census": "census_zcta_county_relationship",
    "nppes": "nppes_npi_registry",
    "geocode": "census_geocoder",
    "ahrq": "ahrq_compendium_hospital_linkage",
    "relationships": "manual_relationships",
    "hcpcs": "cms_hcpcs_level2",
    "msdrg": "cms_ms_drg_table5",
    "websites": "facility_websites",
    "aliases": "manual_relationships",
    "find_websites": "facility_websites",
    "discover": "cms_hpt_txt_discovery",
    "manual_sources": "cms_hpt_txt_discovery",
    "probe": "cms_hpt_txt_discovery",
    "price_files": "price_file_check",
    "catalog": "service_catalog",
    "health_centers": "hrsa_health_center_sites",
    "resolve_plans": "price_file_check",
}


def _engine() -> Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set (see .env.example)")
    from procedurescout_core.db_url import sqlalchemy_url

    return create_engine(sqlalchemy_url(url))


def _run(
    engine: Engine,
    dataset: str,
    work: Callable[[Connection], LoadStats],
    *,
    blob: SourceBlob | None = None,
    source_url: str | None = None,
    source_file: str | None = None,
    source_modified: date | None = None,
    sha256: str | None = None,
    nbytes: int | None = None,
    parameters: dict[str, Any] | None = None,
    commits_inside: bool = False,
) -> LoadStats:
    """commits_inside: the work commits as it goes (production price loading,
    one file at a time, D-054); otherwise everything is one transaction."""
    with engine.begin() as conn:
        load_id: uuid.UUID = begin_load(
            conn,
            dataset,
            source_url=source_url or (blob.url if blob else None),
            source_file=source_file or (blob.path if blob else None),
            source_modified=source_modified,
            sha256=sha256 or (blob.sha256 if blob else None),
            nbytes=nbytes if nbytes is not None else (len(blob.data) if blob else None),
            parameters=parameters,
        )
    try:
        if commits_inside:
            with engine.connect() as conn:
                stats = work(conn)
                finish_load(conn, load_id, stats)
                conn.commit()
        else:
            with engine.begin() as conn:
                stats = work(conn)
                finish_load(conn, load_id, stats)
    except Exception as exc:
        with engine.begin() as conn:
            fail_load(conn, load_id, f"{type(exc).__name__}: {exc}")
        raise
    print(
        json.dumps(
            {
                "dataset": dataset,
                "load_id": str(load_id),
                "rows_in": stats.rows_in,
                "rows_loaded": stats.rows_loaded,
                "rows_rejected": stats.rows_rejected,
                "warnings": len(stats.rejects) - stats.rows_rejected,
                "summary": stats.summary,
            },
            sort_keys=True,
            default=str,
        )
    )
    return stats


def cmd_pdc(args: argparse.Namespace, engine: Engine, kind: str) -> None:
    dataset_id = (
        cms_pdc.HOSPITAL_GENERAL_INFORMATION if kind == "hospitals" else cms_pdc.ASC_FACILITY
    )
    loader = facilities.load_hospitals if kind == "hospitals" else facilities.load_ascs
    name = "cms_hospital_general_information" if kind == "hospitals" else "cms_asc_facility"
    params = {"state": args.state, "dataset_id": dataset_id}
    if args.csv:
        blob = acquire(args.csv)
        rows = cms_pdc.read_csv_rows(blob.data, args.state)
        as_of = date.fromisoformat(args.as_of) if args.as_of else None
        _run(
            engine,
            name,
            lambda c: loader(c, rows, args.state, as_of),
            blob=blob,
            source_modified=as_of,
            parameters=params,
        )
        return
    with new_client() as client:
        got = cms_pdc.fetch_state_rows(client, dataset_id, args.state)
    _run(
        engine,
        name,
        lambda c: loader(c, got.rows, args.state, got.modified),
        source_url=got.source_url,
        source_modified=got.modified,
        sha256=got.sha256,
        nbytes=got.nbytes,
        parameters=params,
    )


def cmd_census(args: argparse.Namespace, engine: Engine) -> None:
    with new_client() as client:
        rel = acquire(args.relationship, client)
        gaz = acquire(args.gazetteer, client)
    _, rel_bytes = maybe_unzip(rel, lambda n, _d: n.lower().endswith(".txt"))
    gaz_name, gaz_bytes = maybe_unzip(gaz, lambda n, _d: n.lower().endswith(".txt"))
    label = f"census_gazetteer_{args.gazetteer_year}+rel2020"
    _run(
        engine,
        "census_zcta_county_relationship",
        lambda c: census.load_census_lookups(
            c,
            decode_text(rel_bytes),
            decode_text(gaz_bytes),
            args.state,
            args.gazetteer_year,
            label,
        ),
        blob=rel,
        parameters={
            "state": args.state,
            "gazetteer": gaz.url or gaz.path,
            "gazetteer_member": gaz_name,
            "gazetteer_sha256": gaz.sha256,
            "gazetteer_year": args.gazetteer_year,
        },
    )


def cmd_nppes(args: argparse.Namespace, engine: Engine) -> None:
    with new_client() as client:
        lookup = nppes.npi_lookup(client)
        _run(
            engine,
            "nppes_npi_registry",
            lambda c: nppes.enrich_asc_addresses(c, args.state, lookup),
            source_url=nppes.NPPES_API,
            parameters={"state": args.state},
        )


def cmd_geocode(args: argparse.Namespace, engine: Engine) -> None:
    with new_client() as client:
        coder = None if args.no_census else (lambda rows: census.census_geocode(client, rows))
        _run(
            engine,
            "census_geocoder",
            lambda c: geocode.geocode_facilities(c, args.state, coder),
            source_url=census.GEOCODER_BATCH_URL,
            parameters={
                "state": args.state,
                "benchmark": census.GEOCODER_BENCHMARK,
                "vintage": census.GEOCODER_VINTAGE,
                "census": not args.no_census,
            },
        )


def cmd_ahrq(args: argparse.Namespace, engine: Engine) -> None:
    with new_client() as client:
        blob = acquire(args.file, client)
    _, data = maybe_unzip(blob, lambda n, _d: n.lower().endswith(".csv"))
    rows = ahrq.parse_linkage(decode_text(data))
    _run(
        engine,
        "ahrq_compendium_hospital_linkage",
        lambda c: ahrq.load_linkage(c, rows, args.state, args.year),
        blob=blob,
        parameters={"state": args.state, "year": args.year},
    )


def cmd_relationships(args: argparse.Namespace, engine: Engine) -> None:
    blob = acquire(args.file)
    _run(
        engine,
        "manual_relationships",
        lambda c: relationships.load_reviewed_relationships(c, decode_text(blob.data)),
        blob=blob,
    )


def cmd_websites(args: argparse.Namespace, engine: Engine) -> None:
    blob = acquire(args.file)
    _run(
        engine,
        "facility_websites",
        lambda c: websites.load_websites(c, decode_text(blob.data)),
        blob=blob,
    )


def cmd_aliases(args: argparse.Namespace, engine: Engine) -> None:
    blob = acquire(args.file)
    _run(
        engine,
        "manual_relationships",
        lambda c: websites.load_reviewed_aliases(c, decode_text(blob.data)),
        blob=blob,
        parameters={"kind": "reviewed_aliases"},
    )


def cmd_discover(args: argparse.Namespace, engine: Engine) -> None:
    from pathlib import Path

    captured_stats = LoadStats()
    manifest = Path(CAPTURED_DIR) / "manifest.csv"
    captured = (
        discovery.load_captured_copies(
            Path(CAPTURED_DIR).resolve(), manifest.read_text(), captured_stats
        )
        if manifest.exists()
        else {}
    )

    home_dir = os.environ.get("HPT_HOME_DIR")
    home = discovery.load_home_fetches(Path(home_dir).resolve(), captured_stats) if home_dir else {}

    def work(c: Connection) -> LoadStats:
        co_listed = (
            discovery.load_co_listed(c, Path(CO_LISTED_CSV).read_text(), captured_stats)
            if Path(CO_LISTED_CSV).exists()
            else {}
        )
        stats = discovery.discover(c, args.state, fetch, captured, home, co_listed)
        stats.summary["home_fetches_available"] = len(home)
        stats.rejects.extend(captured_stats.rejects)
        stats.summary.update({f"manifest_{k}": v for k, v in captured_stats.summary.items()})
        stats.summary["captured_copies_available"] = len(captured)
        return stats

    with new_client() as client:
        fetch = discovery.http_fetcher(client)
        _run(
            engine,
            "cms_hpt_txt_discovery",
            work,
            source_file="approved websites /cms-hpt.txt",
            parameters={"state": args.state},
        )


def cmd_manual_sources(args: argparse.Namespace, engine: Engine) -> None:
    blob = acquire(args.file)
    _run(
        engine,
        "cms_hpt_txt_discovery",
        lambda c: discovery.load_manual_sources(c, decode_text(blob.data)),
        blob=blob,
        parameters={"kind": "manual_sources"},
    )


def cmd_probe(args: argparse.Namespace, engine: Engine) -> None:
    with new_client() as client:
        prober = discovery.http_prober(client)
        _run(
            engine,
            "cms_hpt_txt_discovery",
            lambda c: discovery.probe_sources(c, prober, getattr(args, "state", None)),
            source_file="known price-file URLs (headers only)",
            parameters={"kind": "probe", "state": getattr(args, "state", None)},
        )


def _local_only(url: str) -> str:
    """The work database must be on this computer: never the live one."""
    from sqlalchemy.engine import make_url

    host = make_url(url.replace("postgresql+psycopg://", "postgresql://")).host or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit(f"WORK_DATABASE_URL must point at this computer, not {host!r}")
    return url


def cmd_prepare_work_db(args: argparse.Namespace, engine: Engine) -> None:
    """Make the throwaway work database (already migrated) ready for staging:
    price rows there point at hospitals and datasets that live in the live
    database, so those links are dropped; the checks on every price stay."""
    from procedurescout_core.db_url import sqlalchemy_url

    url = _local_only(os.environ.get("WORK_DATABASE_URL", ""))
    work = create_engine(sqlalchemy_url(url))
    with work.begin() as c:
        for fk in (
            "price_dataset_version_id_fkey",
            "price_facility_id_fkey",
            "price_payer_id_fkey",
            "price_plan_id_fkey",
        ):
            c.execute(text(f"ALTER TABLE price.price DROP CONSTRAINT IF EXISTS {fk}"))
        for idx in ("price.price_code_facility_idx", "price.price_plan_code_idx"):
            c.execute(text(f"DROP INDEX IF EXISTS {idx}"))
    print("work database ready (links to the live database dropped; price checks kept)")


def cmd_clear_staged(args: argparse.Namespace, engine: Engine) -> None:
    """Free the live database's disk (D-059): files still waiting from runs that
    staged prices there are set aside with a reason, and every staged price
    row that isn't the published copy's source is removed. Published prices
    (the Parquet files the site reads) are not touched."""
    from .. import publish

    with engine.begin() as conn:
        waiting = publish.pending_reviews(conn)
        for p in waiting:
            publish.reject(
                conn,
                uuid.UUID(p.dataset_version_id),
                publish.AUTO_REVIEWER,
                "staged in the live database by an earlier run; read again by the next load",
            )
        removed = conn.execute(
            text(
                "DELETE FROM price.price p USING src.dataset_version dv "
                "WHERE dv.id = p.dataset_version_id AND dv.status <> 'published'"
            )
        ).rowcount
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for part in conn.execute(
            text("SELECT relid::regclass::text FROM pg_partition_tree('price.price') WHERE isleaf")
        ).scalars():
            conn.execute(text(f"VACUUM FULL {part}"))
    print(f"set aside {len(waiting)} waiting files; removed {removed} staged price rows")


def cmd_price_files(args: argparse.Namespace, engine: Engine) -> None:
    """Download each assigned price file, check it, delete it (step 2a)."""
    import tempfile
    from pathlib import Path

    from .. import price_files

    max_bytes = int(os.environ.get("PRICE_FILE_MAX_BYTES", price_files.DEFAULT_MAX_BYTES))
    # PRICE_LOAD=1: also read every price into a staged (unpublished) dataset.
    load = os.environ.get("PRICE_LOAD") == "1"
    min_free = int(os.environ.get("PRICE_LOAD_MIN_FREE_BYTES", price_files.DEFAULT_MIN_FREE_BYTES))
    client = httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(60, read=300),
        follow_redirects=True,
    )
    with client, tempfile.TemporaryDirectory(prefix="price-files-") as work:
        downloader = price_files.http_downloader(client, max_bytes)
        home_dir = os.environ.get("HOME_PRICE_DIR")
        if home_dir:
            home = price_files.load_home_price_files(Path(home_dir).resolve())
            print(f"price files available from Cooper's computer: {len(home)}", file=sys.stderr)
            downloader = price_files.with_home_fallback(downloader, home)
        # Production (D-054): publish each facility's file as soon as it passes the
        # automatic checks, remove its staged rows, and commit, one file at a time.
        publish_now = load and os.environ.get("PUBLISH_AS_YOU_GO") == "1"
        allow_first = os.environ.get("AUTO_PUBLISH_FIRST_FILES") == "1"
        after = None
        rows_conn: Connection | None = None
        if publish_now:
            from .. import publish

            store = _store()
            work_url = os.environ.get("WORK_DATABASE_URL", "").strip()
            if work_url:
                # D-059: price rows go to a throwaway database on this computer;
                # the live database only gets the results (files, summaries)
                from procedurescout_core.db_url import sqlalchemy_url

                rows_conn = create_engine(sqlalchemy_url(_local_only(work_url))).connect()

            def after(conn: Connection, facility_id: str) -> None:
                publish.auto_publish_pending(conn, store, allow_first, facility_id, rows=rows_conn)
                publish.prune_published(conn, facility_id)
                conn.commit()
                if rows_conn is not None:
                    rows_conn.commit()

        limit = os.environ.get("PRICE_FILE_LIMIT", "").strip()
        budget = os.environ.get("PRICE_TIME_BUDGET_MINUTES", "").strip()
        stop_at_ns = time.monotonic_ns() + int(budget) * 60 * 10**9 if budget else None
        _run(
            engine,
            "price_file_check",
            lambda c: price_files.check_price_files(
                c,
                args.state,
                downloader,
                Path(work),
                load=load,
                min_free_bytes=min_free,
                after_load=after,
                max_files=int(limit) if limit else None,
                stop_at_ns=stop_at_ns,
                rows_conn=rows_conn,
            ),
            source_file="assigned price files (downloaded, checked, deleted)",
            parameters={
                "state": args.state,
                "max_bytes": max_bytes,
                "load_prices": load,
                "publish_as_you_go": publish_now,
                "auto_publish_first_files": publish_now and allow_first,
                "file_limit": limit or None,
                "rows_on_loading_computer": rows_conn is not None,
                "time_budget_minutes": budget or None,
            },
            commits_inside=publish_now,
        )


def cmd_storage_experiment(args: argparse.Namespace, engine: Engine) -> None:
    """Measure storage layouts for the loaded prices (NAT-02); writes the JSON
    result to storage-experiment.json in the current folder."""
    import tempfile
    from pathlib import Path

    from .. import storage_experiment

    with tempfile.TemporaryDirectory(prefix="parquet-") as work, engine.connect() as conn:
        result = storage_experiment.run(conn, Path(work))
    out = json.dumps(result, indent=2, sort_keys=True, default=str)
    Path("storage-experiment.json").write_text(out)
    print(out)


def _store() -> Any:
    """Folder by default; s3://<bucket> with PRICE_STORE_ENDPOINT, PRICE_STORE_KEY_ID
    and PRICE_STORE_SECRET (a key that can write) for Cloudflare R2 (D-048)."""
    from procedurescout_core.object_store import open_store

    return open_store(
        os.environ.get("PRICE_STORE_DIR", "price-store"),
        os.environ.get("PRICE_STORE_ENDPOINT", ""),
        os.environ.get("PRICE_STORE_KEY_ID", ""),
        os.environ.get("PRICE_STORE_SECRET", ""),
    )


def cmd_send_email(args: argparse.Namespace, engine: Engine) -> None:
    """Send emails waiting in prov.outbox with the configured service (Q26)."""
    from procedurescout_core.mailer import send_pending, sender_from

    sender = sender_from(
        os.environ.get("EMAIL_PROVIDER", ""),
        os.environ.get("EMAIL_FROM", ""),
        os.environ.get("RESEND_API_KEY", ""),
        os.environ.get("SMTP_HOST", ""),
        int(os.environ.get("SMTP_PORT", "587")),
        os.environ.get("SMTP_USERNAME", ""),
        os.environ.get("SMTP_PASSWORD", ""),
    )
    if sender is None:
        print("no email service is set up (EMAIL_PROVIDER, EMAIL_FROM and keys); nothing sent")
        return
    with engine.begin() as conn:
        out = send_pending(conn, sender, limit=args.limit)
    print(f"sent {out.sent}, failed {out.failed}, still waiting {out.waiting}")


def _local(source: str, folder: Path) -> Path:
    """A local copy of a path or https URL (streamed to disk; never held in memory)."""
    if not source.startswith("https://"):
        return Path(source)
    dest = folder / source.rsplit("/", 1)[-1]
    with new_client() as client, client.stream("GET", source) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
    return dest


def cmd_nppes_offices(args: argparse.Namespace, engine: Engine) -> None:
    import tempfile

    from . import nppes_offices as no

    with tempfile.TemporaryDirectory() as tmp:
        npi_file = _local(args.file, Path(tmp))
        nucc = _local(args.nucc, Path(tmp)).read_text(encoding="utf-8", errors="replace")
        map_text = Path(args.map).read_text()
        states = {s.upper() for s in args.state}

        def work(conn: Connection) -> LoadStats:
            stats = LoadStats()
            mapping = no.read_map(map_text, stats)
            if not mapping:
                stats.summary["note"] = "no reviewed taxonomy rows; nothing loaded"
                return stats
            code_types = no.codes_for(nucc, mapping, stats)
            return no.load(
                conn, no.offices(no.open_npi_csv(npi_file), states, code_types, stats), stats
            )

        _run(
            engine,
            no.DATASET,
            work,
            source_url=args.file if args.file.startswith("https://") else None,
            source_file=None if args.file.startswith("https://") else args.file,
            nbytes=npi_file.stat().st_size,
            parameters={"states": sorted(states)},
        )


def _head_reader(client: httpx.Client) -> Callable[[str], bytes]:
    """First 256 KB of a price file (its header), without downloading the rest."""

    def head(url: str) -> bytes:
        if not url.startswith(("https://", "http://")):
            return b""
        out = bytearray()
        with client.stream("GET", url, timeout=30) as r:
            if r.status_code != 200:
                return b""
            for chunk in r.iter_bytes():
                out += chunk
                if len(out) >= 262_144:
                    break
        return bytes(out[:262_144])

    return head


def cmd_verify_websites(args: argparse.Namespace, engine: Engine) -> None:
    from .. import website_verify

    csv_text = Path(args.file).read_text()
    with new_client() as client:

        def fetch(url: str) -> tuple[int, str]:
            r = client.get(url, timeout=30)
            return r.status_code, r.text[:2_000_000]

        _run(
            engine,
            "facility_websites",
            lambda c: website_verify.verify(
                c, csv_text, fetch, LoadStats(), head=_head_reader(client)
            ),
            source_file=args.file,
        )


def cmd_find_websites(args: argparse.Namespace, engine: Engine) -> None:
    from .. import website_verify

    with new_client() as client:

        def get_json(url: str, params: dict[str, str]) -> Any:
            r = client.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()

        def fetch(url: str) -> tuple[int, str]:
            r = client.get(url, timeout=30)
            return r.status_code, r.text[:2_000_000]

        candidates = website_verify.dolthub_candidates(get_json, args.state)
        _run(
            engine,
            "facility_websites",
            lambda c: website_verify.verify(
                c, candidates, fetch, LoadStats(), head=_head_reader(client)
            ),
            source_url=website_verify.DOLTHUB_SQL,
            parameters={"state": args.state, "candidates": candidates.count("\n") - 1},
        )


def cmd_prune_published(args: argparse.Namespace, engine: Engine) -> None:
    from .. import publish

    with engine.begin() as conn:
        n = publish.prune_published(conn)
    print(f"removed {n} staged rows of published files")


def cmd_set_plan(args: argparse.Namespace, engine: Engine) -> None:
    from decimal import Decimal

    from procedurescout_core import billing

    with engine.begin() as conn:
        billing.set_plan(
            conn,
            code=args.code,
            name=args.name,
            kind=args.kind,
            amount=Decimal(args.amount),
            provider_type=args.provider_type,
            stripe_price_id=args.stripe_price,
            approved_by=args.by,
        )
    print(f"plan {args.code} saved")


def cmd_set_fee_start(args: argparse.Namespace, engine: Engine) -> None:
    from datetime import date as _date

    from procedurescout_core import billing

    with engine.begin() as conn:
        billing.set_fee_start(conn, _date.fromisoformat(args.date) if args.date else None, args.by)
    print("listing fee starts " + args.date if args.date else "listing is free (no fee date)")


def cmd_add_staff(args: argparse.Namespace, engine: Engine) -> None:
    from procedurescout_core.portal_auth import add_staff

    with engine.begin() as conn:
        add_staff(conn, args.email, args.role, args.by)
    print(
        f"{args.email} can now use the review pages as {args.role} (after signing in with "
        "the email link and an authenticator app)"
    )


def cmd_auto_publish(args: argparse.Namespace, engine: Engine) -> None:
    """Publish refreshes of already-approved facilities that pass every check (D-035)."""
    from .. import publish

    with engine.begin() as conn:
        for d in publish.auto_publish_pending(conn, _store()):
            verdict = "published" if d.published else "waits for a person: " + "; ".join(d.reasons)
            print(f"{d.facility_name}: {verdict}")
    cmd_code_index(args, engine)  # newly published codes become searchable


def cmd_review_list(args: argparse.Namespace, engine: Engine) -> None:
    from .. import publish

    with engine.connect() as conn:
        for p in publish.pending_reviews(conn):
            load = p.summary
            print(
                f"{p.dataset_version_id}  {p.ccn or '-'}  {p.facility_name}  "
                f"{p.rows} prices  refused {load.get('rows_rejected', 0)}  "
                f"file date {p.last_updated_raw}  flags {load.get('quality_flags', {})}  "
                f"problems: {p.file_problems or 'none'}"
            )


def cmd_approve(args: argparse.Namespace, engine: Engine) -> None:
    from .. import publish

    with engine.begin() as conn:
        key = publish.approve(
            conn, uuid.UUID(args.dataset), args.reviewer, _store(), note=args.note
        )
    print(f"published {args.dataset} as {key}")
    cmd_code_index(args, engine)


def cmd_reject(args: argparse.Namespace, engine: Engine) -> None:
    from .. import publish

    with engine.begin() as conn:
        publish.reject(conn, uuid.UUID(args.dataset), args.reviewer, args.reason)
    print(f"rejected {args.dataset}")


def cmd_catalog(args: argparse.Namespace, engine: Engine) -> None:
    """Provider types, CMS-based facility types and the service catalog (D-032)."""
    from pathlib import Path

    from . import catalog

    def work(c: Connection) -> LoadStats:
        stats = catalog.load_provider_types(c, Path(PROVIDER_TYPES_CSV).read_text())
        stats.summary["facility_types_assigned"] = catalog.assign_cms_provider_types(c)
        services = catalog.load_services(c, Path(SERVICE_CATALOG_CSV).read_text())
        stats.rows_in += services.rows_in
        stats.rows_loaded += services.rows_loaded
        stats.rejects.extend(services.rejects)
        stats.summary.update({f"services_{k}": v for k, v in services.summary.items()})
        for name, loader, path in (
            ("bundles", catalog.load_bundles, BUNDLES_CSV),
            ("poverty_guidelines", catalog.load_poverty_guidelines, POVERTY_CSV),
            ("assistance_policies", catalog.load_assistance_policies, ASSISTANCE_CSV),
            ("payers", catalog.load_payers, PAYERS_CSV),
            ("payer_aliases", catalog.load_payer_aliases, PAYER_ALIASES_CSV),
            ("synonyms", catalog.load_synonyms, SYNONYMS_CSV),
            ("coverage_limits", catalog.load_coverage_limits, COVERAGE_CSV),
        ):
            part = loader(c, Path(path).read_text())
            stats.rows_in += part.rows_in
            stats.rows_loaded += part.rows_loaded
            stats.rejects.extend(part.rejects)
            stats.summary[f"{name}_loaded"] = part.rows_loaded
            stats.summary.update({f"{name}_{k}": v for k, v in part.summary.items()})
        return stats

    _run(engine, "service_catalog", work, source_file="data/reference catalog CSVs")


def cmd_health_centers(args: argparse.Namespace, engine: Engine) -> None:
    """HRSA health center sites for one state (sliding-fee clinics, HELP-01)."""
    from . import health_centers

    with new_client() as client:
        blob = acquire(args.file or health_centers.HRSA_SITES_URL, client)
    _run(
        engine,
        "hrsa_health_center_sites",
        lambda c: health_centers.load_health_centers(c, decode_text(blob.data), args.state),
        blob=blob,
        parameters={"state": args.state},
    )


def cmd_resolve_plans(args: argparse.Namespace, engine: Engine) -> None:
    """Match new insurance spellings when certain; list the rest for Claude (D-047)."""
    from procedurescout_ingest.plan_resolver import resolve_new_spellings

    with engine.begin() as conn:
        res = resolve_new_spellings(conn)
    print(
        json.dumps(
            {
                "dataset": "plan_name_resolution",
                "matched_by_rule": len(res.matched),
                "unresolved": len(res.unresolved),
                "matched": [list(m) for m in res.matched[:50]],
                "unresolved_top": [list(u) for u in res.unresolved[:60]],
            }
        )
    )


def cmd_code_index(args: argparse.Namespace, engine: Engine) -> None:
    """Rebuild the index of billing codes in published prices (D-045)."""
    from procedurescout_ingest.code_index import rebuild_code_index

    with engine.begin() as conn:
        stats = rebuild_code_index(conn)
    print(json.dumps({"dataset": "code_index", "codes": stats.rows_loaded, **stats.summary}))


def cmd_hcpcs(args: argparse.Namespace, engine: Engine) -> None:
    with new_client() as client:
        blob = acquire(args.file, client)
    try:
        member, data = maybe_unzip(blob, codes.looks_like_hcpcs_text)
    except SourceError as exc:
        raise SourceError(f"{exc}; text samples: {codes.describe_text_members(blob.data)}") from exc
    source = f"CMS HCPCS Level II alpha-numeric file, {args.release} ({member})"
    _run(
        engine,
        "cms_hcpcs_level2",
        lambda c: codes.load_hcpcs(c, decode_text(data), args.year, source),
        blob=blob,
        parameters={"release": args.release, "year": args.year, "member": member},
    )


def cmd_msdrg(args: argparse.Namespace, engine: Engine) -> None:
    with new_client() as client:
        blob = acquire(args.file, client)
    if blob.data.startswith(b"PK\x03\x04") and not (blob.path or "").lower().endswith(".xlsx"):
        member, data = codes.pick_table5_member(blob.data)
    else:
        member, data = (blob.path or blob.url or "table5"), blob.data
    source = (
        f"CMS FY{args.fiscal_year} IPPS final rule Table 5, "
        f"MS-DRG v{args.grouper_version} ({member})"
    )
    _run(
        engine,
        "cms_ms_drg_table5",
        lambda c: codes.load_msdrg(
            c, member, data, args.grouper_version, args.fiscal_year, source, min_rows=args.min_rows
        ),
        blob=blob,
        parameters={
            "fiscal_year": args.fiscal_year,
            "grouper_version": args.grouper_version,
            "member": member,
        },
    )


def cmd_report(args: argparse.Namespace, engine: Engine) -> None:
    queries = {
        "facilities_by_type": """
            SELECT facility_type::text, count(*) FROM ref.facility
            WHERE state_code = :s GROUP BY 1 ORDER BY 1""",
        "geocode_precision": """
            SELECT coalesce(geocode_precision, 'none'), count(*) FROM ref.facility
            WHERE state_code = :s GROUP BY 1 ORDER BY 1""",
        "with_county_fips": """
            SELECT county_fips IS NOT NULL, count(*) FROM ref.facility
            WHERE state_code = :s GROUP BY 1 ORDER BY 1""",
        "with_health_system": """
            SELECT health_system_id IS NOT NULL, count(*) FROM ref.facility
            WHERE state_code = :s GROUP BY 1 ORDER BY 1""",
        "rated": """
            SELECT cms_overall_rating IS NOT NULL, count(*) FROM ref.facility
            WHERE state_code = :s GROUP BY 1 ORDER BY 1""",
        "zctas": "SELECT 'zcta', count(*) FROM ref.zcta WHERE state_code = :s",
        "counties": "SELECT 'county', count(*) FROM ref.county WHERE state_code = :s",
        "codes": """
            SELECT system::text || ' ' || version, count(*) FROM ref.code
            GROUP BY 1 ORDER BY 1""",
        "ambiguous_alias_names": """
            SELECT 'names shared by >1 facility', count(*) FROM (
                SELECT a.alias_normalized FROM ref.facility_alias a
                JOIN ref.facility f ON f.id = a.facility_id WHERE f.state_code = :s
                GROUP BY 1 HAVING count(DISTINCT a.facility_id) > 1) x""",
        "websites_approved": """
            SELECT website IS NOT NULL, count(*) FROM ref.facility
            WHERE state_code = :s AND facility_type <> 'ambulatory_surgery_center'
            GROUP BY 1 ORDER BY 1""",
        "hpt_entries": """
            SELECT match_status, count(*) FROM src.hpt_txt_entry GROUP BY 1 ORDER BY 1""",
        "transparency_sources": """
            SELECT facility_id IS NOT NULL, count(*) FROM src.transparency_source
            GROUP BY 1 ORDER BY 1""",
        "loads": """
            SELECT dataset || ' ' || status, count(*) FROM src.reference_load
            GROUP BY 1 ORDER BY 1""",
    }
    out: dict[str, dict[str, int]] = {}
    with engine.connect() as conn:
        for key, sql in queries.items():
            out[key] = {str(k): int(v) for k, v in conn.execute(text(sql), {"s": args.state})}
    print(json.dumps(out, indent=2, sort_keys=True))


def cmd_nv_all(args: argparse.Namespace, engine: Engine) -> None:
    """Run every step even if one fails, so one run shows every problem;
    exit non-zero at the end if any step failed."""
    ns = argparse.Namespace
    st = args.state
    failures: list[str] = []

    def load_count() -> int:
        with engine.connect() as conn:
            return int(conn.execute(text("SELECT count(*) FROM src.reference_load")).scalar_one())

    def step(name: str, fn: Callable[[], None]) -> None:
        before = load_count()
        try:
            fn()
        except Exception as exc:
            failures.append(name)
            message = f"{type(exc).__name__}: {exc}"
            print(f"STEP FAILED: {name}: {message}", file=sys.stderr)
            if load_count() == before:
                # Failed before its lineage row existed (e.g. while downloading or
                # unzipping): record it so the failure shows up in the load report.
                with engine.begin() as conn:
                    load_id = begin_load(conn, STEP_DATASETS[name], source_file=f"nv-all:{name}")
                    fail_load(conn, load_id, message)

    step("hospitals", lambda: cmd_pdc(ns(state=st, csv=None, as_of=None), engine, "hospitals"))
    step("ascs", lambda: cmd_pdc(ns(state=st, csv=None, as_of=None), engine, "ascs"))
    step(
        "census",
        lambda: cmd_census(
            ns(
                state=st,
                relationship=ZCTA_COUNTY_REL_URL,
                gazetteer=GAZETTEER_2026_URL,
                gazetteer_year=2026,
            ),
            engine,
        ),
    )
    step("nppes", lambda: cmd_nppes(ns(state=st), engine))
    step("geocode", lambda: cmd_geocode(ns(state=st, no_census=False), engine))
    if args.ahrq_file:
        step(
            "ahrq", lambda: cmd_ahrq(ns(state=st, file=args.ahrq_file, year=args.ahrq_year), engine)
        )
    else:
        print("AHRQ step skipped: pass --ahrq-file (hospital linkage CSV)", file=sys.stderr)
    if os.path.exists(RELATIONSHIPS_CSV):
        step("relationships", lambda: cmd_relationships(ns(file=RELATIONSHIPS_CSV), engine))
    step(
        "hcpcs",
        lambda: cmd_hcpcs(ns(file=HCPCS_OCT_2026_URL, release="2026-10", year=2026), engine),
    )
    step(
        "msdrg",
        lambda: cmd_msdrg(
            ns(file=MSDRG_FY2027_TABLE5_URL, fiscal_year=2027, grouper_version=44, min_rows=700),
            engine,
        ),
    )
    if os.path.exists(ALIASES_CSV):
        step("aliases", lambda: cmd_aliases(ns(file=ALIASES_CSV), engine))
    step("catalog", lambda: cmd_catalog(ns(), engine))
    step("health_centers", lambda: cmd_health_centers(ns(state=st, file=None), engine))
    if os.path.exists(WEBSITES_CSV):
        step("websites", lambda: cmd_websites(ns(file=WEBSITES_CSV), engine))
    # hospitals still without a website: candidates checked by their cms-hpt.txt (D-048)
    step("find_websites", lambda: cmd_find_websites(ns(state=st), engine))
    step("discover", lambda: cmd_discover(ns(state=st), engine))
    if os.path.exists(MANUAL_SOURCES_CSV):
        step("manual_sources", lambda: cmd_manual_sources(ns(file=MANUAL_SOURCES_CSV), engine))
    step("probe", lambda: cmd_probe(ns(state=st), engine))
    if os.environ.get("PRICE_FILE_DOWNLOADS") == "1":
        # Large downloads (about 5 GB for Nevada): only when the run asks for it.
        step("price_files", lambda: cmd_price_files(ns(state=st), engine))
        if os.environ.get("PRICE_LOAD") == "1":
            step("resolve_plans", lambda: cmd_resolve_plans(ns(), engine))
        if os.environ.get("PRICE_LOAD") == "1" and os.environ.get("PUBLISH_AS_YOU_GO") != "1":
            try:
                cmd_storage_experiment(ns(), engine)
            except Exception as exc:  # a measurement; never fails the run
                print(f"storage experiment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    else:
        print("price-file downloads skipped (PRICE_FILE_DOWNLOADS is not 1)", file=sys.stderr)
    cmd_report(ns(state=st), engine)
    if failures:
        sys.exit(f"{len(failures)} step(s) failed: {', '.join(failures)}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="procedurescout_ingest.reference.cli")
    sub = p.add_subparsers(dest="command", required=True)

    def state(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--state", default="NV", type=str.upper)

    for kind in ("hospitals", "ascs"):
        sp = sub.add_parser(kind, help=f"CMS Provider Data Catalog {kind} for one state")
        state(sp)
        sp.add_argument("--csv", help="read a downloaded CSV instead of the API")
        sp.add_argument("--as-of", help="dataset modified date (YYYY-MM-DD) when using --csv")

    sp = sub.add_parser("census", help="ref.county + ref.zcta from Census files")
    state(sp)
    sp.add_argument("--relationship", default=ZCTA_COUNTY_REL_URL)
    sp.add_argument("--gazetteer", default=GAZETTEER_2026_URL)
    sp.add_argument("--gazetteer-year", type=int, default=2026)

    sp = sub.add_parser("nppes", help="ASC street addresses from the NPI Registry")
    state(sp)

    sp = sub.add_parser("geocode", help="county FIPS + coordinates for facilities")
    state(sp)
    sp.add_argument("--no-census", action="store_true", help="ZCTA centroids only")

    sp = sub.add_parser("ahrq", help="AHRQ Compendium hospital linkage (health systems)")
    state(sp)
    sp.add_argument("--file", required=True, help="path or URL of the linkage CSV")
    sp.add_argument("--year", type=int, required=True, help="Compendium year, e.g. 2023")

    sp = sub.add_parser("relationships", help="reviewed campus/licence relationships CSV")
    sp.add_argument("--file", default=RELATIONSHIPS_CSV)

    sp = sub.add_parser("websites", help="approved facility websites")
    sp.add_argument("--file", default=WEBSITES_CSV)

    sp = sub.add_parser("aliases", help="reviewed facility aliases")
    sp.add_argument("--file", default=ALIASES_CSV)

    sp = sub.add_parser("discover", help="read cms-hpt.txt on approved websites")
    state(sp)

    sp = sub.add_parser("manual-sources", help="reviewed hand-entered price-file links")
    sp.add_argument("--file", default=MANUAL_SOURCES_CSV)

    sp = sub.add_parser("probe", help="size/date check of known price files (no download)")
    sp.add_argument("--state", default=None, type=str.upper, help="only this state's files")
    sub.add_parser("storage-experiment", help="measure storage layouts for loaded prices")
    sub.add_parser("prepare-work-db", help="ready the throwaway work database (D-059)")
    sub.add_parser("clear-staged", help="free the live database's disk of staged rows (D-059)")

    sub.add_parser(
        "catalog", help="provider types, services, bundles, poverty guidelines, policies"
    )
    sub.add_parser("auto-publish", help="publish clean refreshes of approved facilities (D-035)")
    sp = sub.add_parser("send-email", help="send emails waiting in prov.outbox")
    sp.add_argument("--limit", type=int, default=200)
    sp = sub.add_parser("nppes-offices", help="offices from the national provider list (D-052)")
    sp.add_argument("--file", required=True, help="NPPES zip or CSV (path or https URL)")
    sp.add_argument("--nucc", required=True, help="NUCC taxonomy CSV (path or https URL)")
    sp.add_argument("--state", action="append", required=True, help="repeat for several")
    sp.add_argument(
        "--map",
        default=str(Path(__file__).resolve().parents[4] / "data/reference/nppes_taxonomy_map.csv"),
    )
    sp = sub.add_parser(
        "verify-websites", help="accept proposed hospital websites whose cms-hpt.txt names them"
    )
    sp.add_argument("--file", required=True, help="CSV with ccn,url,source")
    sp = sub.add_parser(
        "find-websites", help="candidate hospital websites, verified by their cms-hpt.txt"
    )
    sp.add_argument("--state", required=True, type=str.upper)
    sub.add_parser("prune-published", help="remove staged rows of published files (D-054)")
    sp = sub.add_parser("set-plan", help="add or change a paid plan (Cooper's decision, D-051)")
    sp.add_argument("--code", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--kind", choices=["listing", "sponsored"], required=True)
    sp.add_argument("--amount", required=True, help="dollars per month, e.g. 250")
    sp.add_argument("--provider-type", help="e.g. dental_office; leave out for any business")
    sp.add_argument("--stripe-price", help="Stripe price id (price_...)")
    sp.add_argument("--by", required=True)
    sp = sub.add_parser("set-fee-start", help="when the listing fee starts (default: free)")
    sp.add_argument("--date", help="YYYY-MM-DD; leave out to make listing free again")
    sp.add_argument("--by", required=True)
    sp = sub.add_parser("add-staff", help="let a person use the review pages (ADM-02)")
    sp.add_argument("--email", required=True)
    sp.add_argument("--role", choices=["reviewer", "admin"], default="reviewer")
    sp.add_argument("--by", required=True, help="who is granting access")
    sub.add_parser("review-list", help="staged price datasets waiting for a person's review")
    sp = sub.add_parser("approve", help="publish a reviewed dataset (writes its Parquet file)")
    sp.add_argument("--dataset", required=True, help="dataset version id from review-list")
    sp.add_argument("--reviewer", required=True, help="your name")
    sp.add_argument("--note", help="what you checked")
    sp = sub.add_parser("reject", help="reject a staged dataset with a reason")
    sp.add_argument("--dataset", required=True)
    sp.add_argument("--reviewer", required=True)
    sp.add_argument("--reason", required=True)

    sp = sub.add_parser(
        "price-files", help="download, check and delete each assigned price file (large)"
    )
    state(sp)

    sub.add_parser("code-index", help="rebuild the index of codes in published prices")
    sub.add_parser("resolve-plans", help="match new insurance spellings when certain")
    sp = sub.add_parser("health-centers", help="HRSA health center sites for a state")
    state(sp)
    sp.add_argument("--file", default=None, help="CSV path or URL (default: HRSA download)")
    sp = sub.add_parser("hcpcs", help="HCPCS Level II codes")
    sp.add_argument("--file", default=HCPCS_OCT_2026_URL)
    sp.add_argument("--release", default="2026-10")
    sp.add_argument("--year", type=int, default=2026)

    sp = sub.add_parser("msdrg", help="MS-DRG titles from IPPS Table 5")
    sp.add_argument("--file", default=MSDRG_FY2027_TABLE5_URL)
    sp.add_argument("--fiscal-year", type=int, default=2027)
    sp.add_argument("--grouper-version", type=int, default=44)
    sp.add_argument("--min-rows", type=int, default=700)

    sp = sub.add_parser("report", help="counts for one state")
    state(sp)

    sp = sub.add_parser("nv-all", help="the standard sequence for one state")
    state(sp)
    sp.add_argument("--ahrq-file")
    sp.add_argument("--ahrq-year", type=int, default=2023)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    engine = _engine()
    try:
        handlers: dict[str, Callable[[], None]] = {
            "hospitals": lambda: cmd_pdc(args, engine, "hospitals"),
            "ascs": lambda: cmd_pdc(args, engine, "ascs"),
            "census": lambda: cmd_census(args, engine),
            "nppes": lambda: cmd_nppes(args, engine),
            "geocode": lambda: cmd_geocode(args, engine),
            "ahrq": lambda: cmd_ahrq(args, engine),
            "relationships": lambda: cmd_relationships(args, engine),
            "hcpcs": lambda: cmd_hcpcs(args, engine),
            "websites": lambda: cmd_websites(args, engine),
            "aliases": lambda: cmd_aliases(args, engine),
            "discover": lambda: cmd_discover(args, engine),
            "manual-sources": lambda: cmd_manual_sources(args, engine),
            "probe": lambda: cmd_probe(args, engine),
            "prepare-work-db": lambda: cmd_prepare_work_db(args, engine),
            "clear-staged": lambda: cmd_clear_staged(args, engine),
            "price-files": lambda: cmd_price_files(args, engine),
            "storage-experiment": lambda: cmd_storage_experiment(args, engine),
            "review-list": lambda: cmd_review_list(args, engine),
            "catalog": lambda: cmd_catalog(args, engine),
            "health-centers": lambda: cmd_health_centers(args, engine),
            "code-index": lambda: cmd_code_index(args, engine),
            "resolve-plans": lambda: cmd_resolve_plans(args, engine),
            "auto-publish": lambda: cmd_auto_publish(args, engine),
            "send-email": lambda: cmd_send_email(args, engine),
            "add-staff": lambda: cmd_add_staff(args, engine),
            "set-plan": lambda: cmd_set_plan(args, engine),
            "prune-published": lambda: cmd_prune_published(args, engine),
            "nppes-offices": lambda: cmd_nppes_offices(args, engine),
            "verify-websites": lambda: cmd_verify_websites(args, engine),
            "find-websites": lambda: cmd_find_websites(args, engine),
            "set-fee-start": lambda: cmd_set_fee_start(args, engine),
            "approve": lambda: cmd_approve(args, engine),
            "reject": lambda: cmd_reject(args, engine),
            "msdrg": lambda: cmd_msdrg(args, engine),
            "report": lambda: cmd_report(args, engine),
            "nv-all": lambda: cmd_nv_all(args, engine),
        }
        handlers[args.command]()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
