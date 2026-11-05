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
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from . import ahrq, census, cms_pdc, codes, facilities, geocode, nppes, relationships
from .common import (
    LoadStats,
    SourceBlob,
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


def _engine() -> Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set (see .env.example)")
    return create_engine(url)


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
) -> LoadStats:
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
        coder = None if args.no_census else (lambda rows: census.census_batch_geocode(client, rows))
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


def cmd_hcpcs(args: argparse.Namespace, engine: Engine) -> None:
    with new_client() as client:
        blob = acquire(args.file, client)
    member, data = maybe_unzip(blob, codes.looks_like_hcpcs_text)
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

    def step(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:
            failures.append(name)
            print(f"STEP FAILED: {name}: {type(exc).__name__}: {exc}", file=sys.stderr)

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
            "msdrg": lambda: cmd_msdrg(args, engine),
            "report": lambda: cmd_report(args, engine),
            "nv-all": lambda: cmd_nv_all(args, engine),
        }
        handlers[args.command]()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
