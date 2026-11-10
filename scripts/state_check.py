"""Check that one state works end to end after a load (the all-states test run).

Run after `nv-all --state XX` against the same database. It counts what was
loaded, then asks the real API (as the restricted API role, reading the
published Parquet files) for nearby places, cities and a priced search, and
writes one JSON line to state-check.json plus a Markdown row to
state-check.md. Exit code 1 only for real breakage (no hospitals loaded, an
API error, or published prices the API cannot read); a state whose price
files were not part of the run is not a failure.

    python scripts/state_check.py --state NV --expect-prices
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from sqlalchemy import create_engine, text


def counts(url: str, st: str) -> dict[str, Any]:
    eng = create_engine(url)
    q = {
        "hospitals": "SELECT count(*) FROM ref.facility WHERE state_code = :s "
        "AND facility_type::text LIKE '%hospital'",
        "surgery_centers": "SELECT count(*) FROM ref.facility WHERE state_code = :s "
        "AND facility_type = 'ambulatory_surgery_center'",
        "with_location": "SELECT count(*) FROM ref.facility WHERE state_code = :s "
        "AND geom IS NOT NULL",
        "hospitals_with_website": "SELECT count(*) FROM ref.facility WHERE state_code = :s "
        "AND facility_type::text LIKE '%hospital' AND website IS NOT NULL",
        "price_links_found": "SELECT count(DISTINCT s.facility_id) FROM src.transparency_source s "
        "JOIN ref.facility f ON f.id = s.facility_id WHERE f.state_code = :s",
        "files_downloaded": "SELECT count(DISTINCT t.id) FROM src.transparency_file t "
        "JOIN src.file_facility ff ON ff.file_id = t.id JOIN ref.facility f "
        "ON f.id = ff.facility_id WHERE f.state_code = :s",
        "download_failures": "SELECT count(*) FROM src.reference_reject r "
        "JOIN src.reference_load l ON l.id = r.load_id "
        "WHERE l.dataset = 'price_file_check' AND r.rule = 'download_failed' "
        "AND l.parameters->>'state' = :s",
        "load_failures": "SELECT count(*) FROM src.reference_reject r "
        "JOIN src.reference_load l ON l.id = r.load_id "
        "WHERE l.dataset = 'price_file_check' AND r.rule = 'load_failed' "
        "AND l.parameters->>'state' = :s",
        "facilities_published": "SELECT count(DISTINCT facility_id) FROM price.published_file "
        "WHERE state_code = :s",
        "published_prices": "SELECT coalesce(sum(rows), 0) FROM price.published_file "
        "WHERE state_code = :s",
        "health_centers": "SELECT count(*) FROM ref.health_center WHERE state_code = :s",
        "coverage_rows": "SELECT count(*) FROM ref.coverage_limit WHERE state_code = :s "
        "AND review_state = 'approved'",
        "failed_steps": "SELECT count(*) FROM src.reference_load WHERE status = 'failed'",
    }
    out: dict[str, Any] = {}
    with eng.connect() as c:
        for k, sql in q.items():
            try:
                out[k] = int(c.execute(text(sql), {"s": st}).scalar_one())
            except Exception as exc:  # report, keep going
                c.rollback()
                out[k] = f"error: {type(exc).__name__}"
        failed = c.execute(
            text("SELECT dataset, left(error, 200) FROM src.reference_load WHERE status = 'failed'")
        ).all()
        out["failed_step_names"] = [f"{r[0]}: {r[1]}" for r in failed]
        sample = c.execute(
            text(
                """
                SELECT f.id, ST_Y(f.geom::geometry), ST_X(f.geom::geometry), s.code_system::text,
                       s.code
                FROM price.published_file p
                JOIN ref.facility f ON f.id = p.facility_id
                JOIN price.file_code_summary s ON s.facility_id = f.id
                WHERE p.state_code = :s AND f.geom IS NOT NULL
                ORDER BY s.prices DESC LIMIT 1
                """
            ),
            {"s": st},
        ).first()
        out["_sample"] = None if sample is None else [str(x) for x in sample]
        any_place = c.execute(
            text(
                "SELECT ST_Y(geom::geometry), ST_X(geom::geometry) FROM ref.facility "
                "WHERE state_code = :s AND geom IS NOT NULL "
                "AND facility_type::text LIKE '%hospital' LIMIT 1"
            ),
            {"s": st},
        ).first()
        out["_place"] = None if any_place is None else [str(x) for x in any_place]
    eng.dispose()
    return out


def api_checks(st: str, place: list[str] | None, sample: list[str] | None) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from procedurescout_api.main import app

    out: dict[str, Any] = {}
    with TestClient(app) as client:
        r = client.get("/v1/places/cities", params={"state": st})
        out["cities"] = len(r.json()) if r.status_code == 200 else f"HTTP {r.status_code}"
        if place:
            r = client.get("/v1/facilities/near", params={"lat": place[0], "lng": place[1]})
            out["nearby"] = len(r.json()) if r.status_code == 200 else f"HTTP {r.status_code}"
        if sample:
            fid, lat, lng, system, code = sample
            r = client.get(f"/v1/facilities/{fid}")
            out["facility_page"] = r.status_code
            found = None
            for mode in ("cash", "list"):
                r = client.get(
                    "/v1/search",
                    params={
                        "lat": lat,
                        "lng": lng,
                        "code_system": system,
                        "code": code,
                        "mode": mode,
                    },
                )
                if r.status_code != 200:
                    out[f"search_{mode}"] = f"HTTP {r.status_code}: {r.text[:200]}"
                    continue
                rows = [f for f in r.json()["facilities"] if f["facility_id"] == fid]
                out[f"search_{mode}"] = rows[0]["headline"] if rows else "facility missing"
                found = found or (rows[0]["headline"] if rows else None)
            out["priced_search_works"] = found is not None
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--state", required=True, type=str.upper)
    p.add_argument("--expect-prices", action="store_true")
    a = p.parse_args()
    owner = os.environ["DATABASE_URL"]
    c = counts(owner, a.state)
    place, sample = c.pop("_place"), c.pop("_sample")
    try:
        c.update(api_checks(a.state, place, sample))
    except Exception as exc:
        c["api_error"] = f"{type(exc).__name__}: {exc}"[:300]
    problems = []
    if not isinstance(c["hospitals"], int) or c["hospitals"] == 0:
        problems.append("no hospitals loaded")
    if c.get("api_error"):
        problems.append("API error")
    for k in ("cities", "nearby", "search_cash", "search_list"):
        if str(c.get(k, "")).startswith("HTTP"):
            problems.append(f"{k} failed")
    if sample and not c.get("priced_search_works"):
        problems.append("published prices not found by search")
    if a.expect_prices and c.get("facilities_published") == 0:
        problems.append("no hospital published (see download/load failures)")
    if c.get("coverage_rows") != 4:
        problems.append("help-paying limits missing")
    c["state"] = a.state
    c["problems"] = problems
    with open("state-check.json", "w") as f:
        f.write(json.dumps(c, default=str) + "\n")
    row = (
        f"| {a.state} | {c['hospitals']} | {c['surgery_centers']} | "
        f"{c['hospitals_with_website']} | {c['price_links_found']} | {c['files_downloaded']} | "
        f"{c['facilities_published']} | {c['download_failures']} | {c['load_failures']} | "
        f"{c.get('cities', '')} | {'yes' if c.get('priced_search_works') else '-'} | "
        f"{'; '.join(problems) or 'ok'} |"
    )
    with open("state-check.md", "w") as f:
        f.write(row + "\n")
    print(json.dumps(c, indent=2, default=str))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
