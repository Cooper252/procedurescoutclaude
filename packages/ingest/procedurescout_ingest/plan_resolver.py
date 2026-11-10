"""Place new hospital insurance spellings automatically when it is certain (D-047).

A new spelling is matched only when both parts are unambiguous:
- the insurer: its normalized spelling already has approved aliases that all
  point to ONE insurer, or it equals an approved insurer's own name; and
- the plan: the plan text is a plain plan type (HMO, PPO, EPO, POS, Medicaid,
  Medicare Advantage, marketplace, "all plans") and that insurer has a card
  name of that type.
Everything else is left unmatched for Claude to research, and stays findable
exactly as written (D-046). Matches are recorded as
reviewed_by = "automatic rule (D-047)" so they can be listed and undone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from procedurescout_core.matching import normalize_name

RULE = "automatic rule (D-047)"
ALL_PLANS = "All plans (one rate published for all)"
_SKIP = re.compile(r"worker|wcomp|\bwc\b|work comp|auto|liability|jail|hospice|behavioral")
_TYPES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"medicare advantage|\bmedicare\b|\bmcr\b|\bma\b|mapd"), "Medicare Advantage"),
    (re.compile(r"medicaid|\bmcd\b|\bmcaid\b|managed medicaid"), "Medicaid plan"),
    (re.compile(r"marketplace|exchange|\bhix\b|\bqhp\b|\bifp\b"), "Marketplace (exchange) plan"),
    (re.compile(r"^(commercial )?hmo$"), "HMO"),
    (re.compile(r"^(commercial )?ppo$"), "PPO"),
    (re.compile(r"^(commercial )?epo$"), "EPO"),
    (re.compile(r"^(commercial )?pos$"), "POS"),
    (re.compile(r"^(all|all plans|all products|commercial|comm|managed care|generic)$"), ALL_PLANS),
]


@dataclass
class Resolution:
    matched: list[tuple[str, str, str, str]] = field(default_factory=list)
    unresolved: list[tuple[str, str, int]] = field(default_factory=list)


def plan_type(plan_raw: str) -> str | None:
    p = normalize_name(plan_raw).replace("_", " ")
    if _SKIP.search(p):
        return None
    for pattern, label in _TYPES:
        if pattern.search(p):
            return label
    return None


def _insurer_for(conn: Connection, payer_key: str) -> str | None:
    ids = (
        conn.execute(
            text(
                """
            SELECT DISTINCT pl.payer_id FROM ref.plan_alias a JOIN ref.plan pl ON pl.id = a.plan_id
            WHERE a.raw_payer_normalized = :k AND a.review_state = 'approved'
            UNION
            SELECT id FROM ref.payer WHERE lower(canonical_name) = :k
            """
            ),
            {"k": payer_key},
        )
        .scalars()
        .all()
    )
    return str(ids[0]) if len(ids) == 1 else None


def resolve_new_spellings(conn: Connection) -> Resolution:
    """New spellings in staged prices and published files' summaries."""
    pairs = conn.execute(
        text(
            """
            SELECT payer_name_raw, plan_name_raw, sum(n) FROM (
                SELECT payer_name_raw, plan_name_raw, count(*) AS n FROM price.price p
                WHERE payer_name_raw IS NOT NULL AND plan_name_raw IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM price.file_payer_summary s
                                  WHERE s.dataset_version_id = p.dataset_version_id)
                GROUP BY 1, 2
                UNION ALL
                -- spellings from published files whose staged rows were removed (D-054)
                SELECT payer_name_raw, plan_name_raw, prices FROM price.file_payer_summary
                WHERE plan_name_raw <> ''
            ) x
            GROUP BY 1, 2
            """
        )
    ).all()
    approved = {
        (str(r[0]), str(r[1]))
        for r in conn.execute(
            text(
                "SELECT raw_payer_normalized, raw_plan_normalized FROM ref.plan_alias "
                "WHERE review_state = 'approved'"
            )
        ).all()
    }
    out = Resolution()
    seen: set[tuple[str, str]] = set()
    for payer_raw, plan_raw, n in pairs:
        key = (normalize_name(str(payer_raw)), normalize_name(str(plan_raw)))
        if key in approved or key in seen:
            continue
        seen.add(key)
        insurer = _insurer_for(conn, key[0])
        label = plan_type(str(plan_raw))
        plan = None
        if insurer is not None and label is not None:
            plan = conn.execute(
                text("SELECT id FROM ref.plan WHERE payer_id = :p AND canonical_name = :n"),
                {"p": insurer, "n": label},
            ).scalar()
        if plan is None:
            out.unresolved.append((str(payer_raw), str(plan_raw), int(n)))
            continue
        conn.execute(
            text(
                """
                INSERT INTO ref.plan_alias (raw_payer_normalized, raw_plan_text,
                    raw_plan_normalized, plan_id, match_type, review_state, reviewed_by,
                    reviewed_at)
                VALUES (:rp, :t, :k, :pl, 'normalized', 'approved', :rb, now())
                ON CONFLICT (raw_payer_normalized, raw_plan_normalized) DO UPDATE SET
                    plan_id = EXCLUDED.plan_id, match_type = 'normalized',
                    review_state = 'approved', reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = EXCLUDED.reviewed_at
                """
            ),
            {"rp": key[0], "t": str(plan_raw), "k": key[1], "pl": plan, "rb": RULE},
        )
        name = conn.execute(
            text("SELECT canonical_name FROM ref.payer WHERE id = :p"), {"p": insurer}
        ).scalar()
        out.matched.append((str(payer_raw), str(plan_raw), str(name), label or ""))
    out.unresolved.sort(key=lambda r: -r[2])
    return out
