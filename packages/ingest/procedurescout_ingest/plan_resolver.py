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

2026-11-12 (Cooper: typing "Medicare" listed "Medicare A AL JJ", "Traditional
Medicare"...): reviewed naming rules (data/reference/payer_name_rules.csv,
written by Claude under D-047) say which insurer a spelling is, e.g. "BCBS_AL",
"BlueCross BlueShield of Alabama" and "Blue Cross of AL" are Blue Cross Blue
Shield of Alabama, and "Medicare A AL JJ" is Original Medicare. More plan
wordings are understood ("Medicare Managed Care Plan", "Managed Medicaid",
"All Commercial Plans", a plan text that only repeats the insurer's name).
Plans that aren't regular health coverage (workers' comp, transplant
contracts, behavioral health carve-outs, prisons) are never matched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from procedurescout_core.matching import normalize_name

RULE = "automatic rule (D-047)"
NAME_RULE = "automatic rule with Claude's reviewed insurer names (D-047)"
ALL_PLANS = "All plans (one rate published for all)"
_SKIP = re.compile(
    r"worker|wcomp|\bwc\b|work comp|auto|liability|jail|hospice|behavioral|\bbh\b|psych"
    r"|transplant|athlet|inmate|prison|correction|vaccine|tricare|\bva\b|veteran|champva"
    r"|dental|vision|supplement|medigap|out of state|rental|network access|catch ?all"
    r"|swing|\birf\b|\brac\b|home health|nursing|student|sick baby|non par|self pay"
    r"|uninsured|research"
)
_TYPES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"medicare advantage|medicare managed care|managed medicare|\bmedicare\b|\bmcr\b"
            r"|\bma\b|mapd|d snp|\bdual\b|medicarecomplete"
        ),
        "Medicare Advantage",
    ),
    (re.compile(r"medicaid|\bmcd\b|\bmcaid\b|rite ?care|\bchip\b"), "Medicaid plan"),
    (
        re.compile(r"marketplace|exchange|\bhix\b|\bqhp\b|\bifp\b|\biex\b|health connect|\baca\b"),
        "Marketplace (exchange) plan",
    ),
    (re.compile(r"^(commercial )?hmo$"), "HMO"),
    (re.compile(r"^(commercial )?ppo$"), "PPO"),
    (re.compile(r"^(commercial )?epo$"), "EPO"),
    (re.compile(r"^(commercial )?pos$"), "POS"),
    (
        re.compile(
            r"^(all|all plans|all products|commercial|comm|managed care|generic|default"
            r"|all commercial plans|all other plans|all payer|all payor|commercial all payer"
            r"|all payor commercial|hmo ppo|hmo pos ppo|commercial hmo ppo)$"
        ),
        ALL_PLANS,
    ),
]
# words that don't change what a plan is, for "Aetna | Aetna Commercial"
_FILLER = set(
    "commercial comm plan plans all products payer payor default other the health healthcare "
    "insurance company inc llc of and group services rates rate complete data network".split()
)
_STATES = set(
    "al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo mt ne nv nh nj "
    "nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy alabama alaska arizona arkansas "
    "california colorado connecticut delaware florida georgia hawaii idaho illinois indiana iowa "
    "kansas kentucky louisiana maine maryland massachusetts michigan minnesota mississippi "
    "missouri montana nebraska nevada ohio oklahoma oregon pennsylvania tennessee texas utah "
    "vermont virginia washington wisconsin wyoming".split()
)
_NO_ADVANTAGE = re.compile(r"advantage|managed|hmo|ppo|replacement|mapd|complete|aarp|\bma\b")


@dataclass(frozen=True)
class NameRule:
    pattern: re.Pattern[str]
    payer: str


def loosen(payer_raw: str) -> str:
    """A payer spelling for the naming rules: lower case, '_' and punctuation as
    spaces, numbers and 'payer'/'inc'/'llc' dropped ('[payer_BCBS DELAWARE ]',
    'BCBS_Alabama', 'AETNA COMMERCIAL [85189]')."""
    t = normalize_name(payer_raw).replace("_", " ")
    words = [w for w in t.split() if not w.isdigit() and w not in ("payer", "inc", "llc", "the")]
    return " ".join(words)


def load_name_rules(csv_text: str) -> list[NameRule]:
    """Reviewed rows only (rule 9, D-047)."""
    import csv
    import io

    out = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        if (row.get("reviewed_by") or "").strip() and (row.get("pattern") or "").strip():
            out.append(NameRule(re.compile(row["pattern"].strip()), row["payer"].strip()))
    return out


def _rule_insurer(conn: Connection, rules: list[NameRule], payer_raw: str) -> str | None:
    key = loosen(payer_raw)
    names = {r.payer for r in rules if r.pattern.fullmatch(key)}
    if len(names) != 1:
        return None
    found = conn.execute(
        text("SELECT id FROM ref.payer WHERE canonical_name = :n"), {"n": names.pop()}
    ).scalar()
    return None if found is None else str(found)


def _only_repeats_insurer(plan_raw: str, payer_raw: str, insurer_name: str) -> bool:
    """'AETNA | AETNA', 'Aetna | Aetna Commercial', 'BCBS | BCBS AL Commercial':
    the plan text adds nothing but the insurer's name, so it is one rate for all
    of that insurer's plans."""
    own = set(loosen(payer_raw).split()) | set(loosen(insurer_name).split())
    rest = [
        w
        for w in normalize_name(plan_raw).replace("_", " ").split()
        if w not in own and w not in _FILLER and w not in _STATES
    ]
    return not rest


@dataclass
class Resolution:
    matched: list[tuple[str, str, str, str]] = field(default_factory=list)
    unresolved: list[tuple[str, str, int]] = field(default_factory=list)


def plan_type(plan_raw: str) -> str | None:
    p = normalize_name(plan_raw).replace("_", " ").replace("/", " ").replace("-", " ")
    p = " ".join(p.split())
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


def _pick_plan(
    conn: Connection, insurer: str, payer_raw: str, plan_raw: str
) -> tuple[str | None, str]:
    """(plan id, label) for one spelling of a known insurer, or (None, '')."""
    p = normalize_name(plan_raw).replace("_", " ")
    if _SKIP.search(p) or _SKIP.search(normalize_name(payer_raw).replace("_", " ")):
        return None, ""
    plans = {
        str(r[0]): str(r[1])
        for r in conn.execute(
            text("SELECT canonical_name, id FROM ref.plan WHERE payer_id = :p"), {"p": insurer}
        ).all()
    }
    name = str(
        conn.execute(
            text("SELECT canonical_name FROM ref.payer WHERE id = :p"), {"p": insurer}
        ).scalar()
    )
    if name == "Original Medicare":  # the government's Medicare, never an Advantage plan
        if _NO_ADVANTAGE.search(p):
            return None, ""
        return plans.get("Original Medicare"), "Original Medicare"
    label = plan_type(plan_raw)
    if label is None and _only_repeats_insurer(plan_raw, payer_raw, name):
        label = ALL_PLANS
    if len(plans) == 1:  # an insurer with one kind of plan (Devoted, a state's Medicaid)
        ((only, pid),) = plans.items()
        repeats = _only_repeats_insurer(plan_raw, payer_raw, name)
        fits = (
            label == only
            or (only == "Medicaid" and label == "Medicaid plan")
            or (label is None and len(p.split()) <= 4)
            or (label == ALL_PLANS and repeats)
        )
        return (pid, only) if fits else (None, "")
    if label is None:
        return None, ""
    return plans.get(label), label


def resolve_new_spellings(conn: Connection, rules: list[NameRule] | None = None) -> Resolution:
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
        by_rule = False
        if insurer is None and rules:
            insurer = _rule_insurer(conn, rules, str(payer_raw))
            by_rule = insurer is not None
        plan, label = (None, "")
        if insurer is not None:
            plan, label = _pick_plan(conn, insurer, str(payer_raw), str(plan_raw))
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
            {
                "rp": key[0],
                "t": str(plan_raw),
                "k": key[1],
                "pl": plan,
                "rb": NAME_RULE if by_rule else RULE,
            },
        )
        name = conn.execute(
            text("SELECT canonical_name FROM ref.payer WHERE id = :p"), {"p": insurer}
        ).scalar()
        out.matched.append((str(payer_raw), str(plan_raw), str(name), label or ""))
    out.unresolved.sort(key=lambda r: -r[2])
    return out
