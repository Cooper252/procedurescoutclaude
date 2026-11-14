"""How many of a state's published prices a person can reach by searching a service.

Cooper (2026-11-14): "we have millions of prices for each state and I'm getting
very few when I search". A service (ref.procedure) finds prices only through
its approved codes, and most services have one code. This measures, for a
state's current published hospital files, how many prices sit under a code
some approved service uses, and lists the procedure codes with the most
places that no service uses yet, with the hospitals' own wording, so services
and codes can be added from them (D-061).

Hospital-internal codes (chargemaster lines, revenue codes, drug NDCs, local
codes) are counted but not listed: they name a hospital's own charge items,
not a procedure anyone searches for.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text

# codes that name a procedure or a hospital stay the same way everywhere
PROCEDURE_SYSTEMS = (
    "CPT",
    "HCPCS",
    "CDT",
    "MS-DRG",
    "APR-DRG",
    "DRG",
    "MS-LTC-DRG",
    "TRIS-DRG",
    "R-DRG",
    "S-DRG",
    "APS-DRG",
    "AP-DRG",
)


def _pct(part: int, whole: int) -> str:
    if whole == 0:
        return "0"
    return str((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1")))


def service_coverage(conn: Connection, state: str, top: int = 40) -> dict[str, Any]:
    by_system: dict[str, dict[str, int]] = {}
    for sys_, prices, covered in conn.execute(
        text(
            """
    WITH cur AS (
        SELECT dataset_version_id FROM src.published_file
        WHERE retired_at IS NULL AND state_code = :s AND price_source = 'hospital_file'
    ),
    codes AS (
        SELECT s.code_system::text AS sys, s.code, s.top_description, s.facility_id, s.prices
        FROM price.file_code_summary s JOIN cur USING (dataset_version_id)
    ),
    svc AS (
        SELECT DISTINCT pc.code_system::text AS sys, pc.code
        FROM ref.procedure_code pc JOIN ref.procedure p ON p.id = pc.procedure_id
        WHERE pc.review_state = 'approved' AND p.review_state = 'approved'
    )

            SELECT c.sys, sum(c.prices),
                   coalesce(sum(c.prices) FILTER (WHERE v.code IS NOT NULL), 0)
            FROM codes c LEFT JOIN svc v ON v.sys = c.sys AND v.code = c.code
            GROUP BY c.sys ORDER BY 2 DESC
            """
        ),
        {"s": state},
    ).all():
        by_system[str(sys_)] = {"prices": int(prices), "in_services": int(covered)}
    total = sum(v["prices"] for v in by_system.values())
    covered = sum(v["in_services"] for v in by_system.values())
    proc = {k: v for k, v in by_system.items() if k in PROCEDURE_SYSTEMS}
    proc_total = sum(v["prices"] for v in proc.values())
    proc_covered = sum(v["in_services"] for v in proc.values())
    uncovered = conn.execute(
        text(
            """
    WITH cur AS (
        SELECT dataset_version_id FROM src.published_file
        WHERE retired_at IS NULL AND state_code = :s AND price_source = 'hospital_file'
    ),
    codes AS (
        SELECT s.code_system::text AS sys, s.code, s.top_description, s.facility_id, s.prices
        FROM price.file_code_summary s JOIN cur USING (dataset_version_id)
    ),
    svc AS (
        SELECT DISTINCT pc.code_system::text AS sys, pc.code
        FROM ref.procedure_code pc JOIN ref.procedure p ON p.id = pc.procedure_id
        WHERE pc.review_state = 'approved' AND p.review_state = 'approved'
    )

            SELECT c.sys, c.code, count(DISTINCT c.facility_id) AS places,
                   sum(c.prices) AS prices, max(c.top_description) AS wording
            FROM codes c LEFT JOIN svc v ON v.sys = c.sys AND v.code = c.code
            WHERE v.code IS NULL AND c.sys = ANY(:systems)
            GROUP BY c.sys, c.code
            ORDER BY places DESC, prices DESC, c.sys, c.code
            LIMIT :n
            """
        ),
        {"s": state, "systems": list(PROCEDURE_SYSTEMS), "n": top},
    ).all()
    return {
        "prices": total,
        "prices_in_services": covered,
        "percent_in_services": _pct(covered, total),
        "procedure_code_prices": proc_total,
        "procedure_code_prices_in_services": proc_covered,
        "percent_of_procedure_code_prices_in_services": _pct(proc_covered, proc_total),
        "by_code_type": by_system,
        "top_procedure_codes_not_in_any_service": [
            f"{s} {c} | {p} places | {n} prices | {(w or '')[:90]}" for s, c, p, n, w in uncovered
        ],
    }
