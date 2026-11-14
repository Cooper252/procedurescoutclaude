"""Every published price option for what a person typed, grouped so a common
person can choose (Cooper, 2026-11-14: "I don't want 2 options, I want 20
options if that's what there is ... There is no reason to have all these prices
and use 1/10th of them").

How it finds options:
- Every billing code in published hospital prices is in ref.code_index with the
  wording hospitals most often publish for it (D-045). We match the person's
  words against that wording, and against the official public titles of
  MS-DRG and HCPCS codes (CMS) where we have them.
- Everyday words are widened to the words hospitals and code titles use
  ("birth" also finds "delivery", "cesarean", "newborn"; "c-section" finds
  "cesarean"). The list is below with its source: the official code-set
  wording (D-061). Nothing is substituted: every option keeps its own code and
  the person picks.
- "Anesthesia" also lists the CPT anesthesia section (codes 00100-01999), whose
  hospital wording often doesn't say "anesthesia". A match on "without
  anesthesia" is not an anesthesia option.
- Options are grouped by kind (hospital stays, anesthesia, surgery, imaging,
  lab tests, visits, drugs, supplies, dental, other, each hospital's own item
  codes last) and ranked by how many places publish a price.

CPT descriptor text is never stored or shown from ref.code (D-002); the wording
shown for CPT codes is the hospitals' own, labeled as theirs by the site.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from sqlalchemy import Connection, text

# group keys, in the order the site shows them
GROUPS = (
    "stay",
    "anesthesia",
    "surgery",
    "imaging",
    "lab",
    "visit",
    "drug",
    "supply",
    "dental",
    "other",
    "hospital_item",
)

# code types that are one hospital's own numbering (or a charge category), not
# a code that means the same thing everywhere
HOSPITAL_ITEM_SYSTEMS = frozenset({"CDM", "LOCAL", "RC", "NDC"})

# Everyday words -> the words hospital price files and official code titles use
# for the same thing. Source: the CMS MS-DRG titles (e.g. 768, 783-788,
# 796-798, 805-807 "VAGINAL DELIVERY ...", "CESAREAN SECTION ..."), APR-DRG
# titles ("NEONATE ...", "VAGINAL DELIVERY"), ICD-10-PCS section 1 "Obstetrics",
# HCPCS Level II titles and the CPT section names (Anesthesia 00100-01999,
# Maternity Care and Delivery 59000-59899). Each entry is a list of
# alternatives; words inside one alternative must all appear. A trailing "*"
# matches the start of a word ("deliv*" finds "delivery", "deliv").
# (Claude, delegated by Cooper, D-061)
WIDEN: dict[str, tuple[str, ...]] = {
    "birth": (
        "vaginal deliv*",
        "vag deliv*",
        "cesarean",
        "caesarean",
        "c-section",
        "labor",
        "obstetric*",
        "newborn",
        "neonat*",
        "antepartum",
        "postpartum",
        "vbac",
    ),
    "childbirth": ("vaginal deliv*", "cesarean", "labor", "obstetric*", "newborn"),
    "baby": ("vaginal deliv*", "cesarean", "newborn", "neonat*", "obstetric*", "infant"),
    "having a baby": ("vaginal deliv*", "cesarean", "labor", "obstetric*"),
    "labor": ("vaginal deliv*", "labor", "obstetric*"),
    "delivery": ("vaginal deliv*", "cesarean", "obstetric*"),
    "pregnan*": ("obstetric*", "antepartum", "prenatal", "fetal", "pregnan*"),
    "prenatal": ("antepartum", "obstetric*", "prenatal", "fetal"),
    "c section": ("cesarean", "caesarean", "c-section", "csection"),
    "c-section": ("cesarean", "caesarean", "c-section", "csection"),
    "csection": ("cesarean", "caesarean", "c-section", "csection"),
    "cesarean": ("cesarean", "caesarean", "c-section", "csection"),
    "caesarean": ("cesarean", "caesarean", "c-section", "csection"),
    "newborn": ("newborn", "neonat*", "infant"),
    "anesthesia": ("anesth*", "anaesth*", "anes", "sedation"),
    "anesthetic": ("anesth*", "anaesth*", "sedation"),
    "anaesthesia": ("anesth*", "anaesth*", "anes"),
    "sedation": ("sedation", "anesth*"),
    "put to sleep": ("anesth*", "sedation"),
    "epidural": ("epidural",),
    "tubes tied": ("sterilization", "tubal ligation", "salpingectomy"),
    "tubal": ("tubal", "sterilization", "salpingectomy"),
    "x-ray": ("x-ray", "xray", "radiologic exam*", "radiograph*", "xr"),
    "xray": ("x-ray", "xray", "radiologic exam*", "radiograph*", "xr"),
    "mri": ("mri", "magnetic resonance"),
    "cat scan": ("ct", "computed tomograph*"),
    "ct scan": ("ct", "computed tomograph*"),
    "ultrasound": ("ultrasound", "ultrason*", "sonogra*", "echo*"),
    "sonogram": ("ultrasound", "sonogra*"),
    "mammogram": ("mammogra*",),
    "blood test": ("blood", "panel", "assay"),
    "er": ("emergency",),
    "emergency room": ("emergency",),
    "knee replacement": ("knee arthroplasty", "knee replac*", "joint replac*"),
    "hip replacement": ("hip arthroplasty", "hip replac*", "joint replac*"),
    "gallbladder": ("cholecystectom*", "gallbladder", "biliary"),
    "appendix": ("appendectom*", "appendix"),
    "tonsils": ("tonsillectom*", "tonsil*", "adenoidectom*"),
    "heart attack": ("myocardial infarction", "acute mi"),
    "stroke": ("stroke", "intracranial hemorrhage", "cerebral infarction"),
    "physical therapy": ("therapeutic exercise*", "physical therapy", "pt eval*"),
    "stitches": ("repair", "laceration", "wound"),
    "hysterectomy": ("hysterectom*",),
    "vasectomy": ("vasectom*",),
    "cataract": ("cataract",),
    "colonoscopy": ("colonoscop*",),
    "endoscopy": ("endoscop*", "egd", "esophagogastroduodenoscop*"),
    "dialysis": ("dialysis", "hemodialysis"),
    "chemo": ("chemotherap*", "chemo"),
    "chemotherapy": ("chemotherap*", "chemo"),
}

# Code ranges that ARE the thing, whatever a hospital wrote for them
# (CMS MS-DRG v42 MDC 14 "Pregnancy, Childbirth" 768, 783-798, 805-807 and
# MDC 15 "Newborns" 789-795; APR-DRG 540-566 obstetrics and 580-640 newborns,
# published with a severity digit, e.g. 5601; CPT Maternity Care and Delivery
# 59000-59899 and obstetric anesthesia 01958-01969). (D-061)
_BIRTH_RANGES: tuple[tuple[str, int, int], ...] = (
    ("MS-DRG", 768, 768),
    ("MS-DRG", 783, 798),
    ("MS-DRG", 805, 807),
    ("APR-DRG", 540, 566),
    ("APR-DRG", 580, 640),
    ("APR-DRG", 5400, 5664),
    ("APR-DRG", 5800, 6404),
    ("CPT", 59000, 59899),
    ("CPT", 1958, 1969),
)
CODE_RANGES: dict[str, tuple[tuple[str, int, int], ...]] = {
    "birth": _BIRTH_RANGES,
    "childbirth": _BIRTH_RANGES,
    "baby": _BIRTH_RANGES,
    "having a baby": _BIRTH_RANGES,
    "labor": _BIRTH_RANGES,
    "c section": (("MS-DRG", 783, 788), ("CPT", 59510, 59622), ("CPT", 1961, 1963)),
    "c-section": (("MS-DRG", 783, 788), ("CPT", 59510, 59622), ("CPT", 1961, 1963)),
    "cesarean": (("MS-DRG", 783, 788), ("CPT", 59510, 59622), ("CPT", 1961, 1963)),
    "newborn": (("MS-DRG", 789, 795), ("APR-DRG", 580, 640), ("APR-DRG", 5800, 6404)),
    "anesthesia": (("CPT", 100, 1999),),
    "anesthetic": (("CPT", 100, 1999),),
    "anaesthesia": (("CPT", 100, 1999),),
}

# CPT sections by code number (the published section ranges of the code set)
_CPT_SECTIONS = (
    (100, 1999, "anesthesia"),
    (10004, 69990, "surgery"),
    (70010, 79999, "imaging"),
    (80047, 89398, "lab"),
    (90281, 99199, "visit"),
    (99202, 99607, "visit"),
)

# HCPCS Level II sections by first letter (CMS HCPCS Level II index)
_HCPCS_LETTER = {
    "A": "supply",
    "B": "supply",
    "E": "supply",
    "K": "supply",
    "L": "supply",
    "V": "supply",
    "Q": "supply",
    "J": "drug",
    "P": "lab",
    "R": "imaging",
    "D": "dental",
}

_STOP = frozenset({"a", "an", "the", "of", "and", "or", "for", "with", "to", "in", "on", "my"})
_WORD = re.compile(r"[a-z0-9]+")


def group_for(system: str, code: str) -> str:
    """Which kind of option a code is."""
    if system in HOSPITAL_ITEM_SYSTEMS:
        return "hospital_item"
    if system.endswith("DRG"):
        return "stay"
    if system == "CDT":
        return "dental"
    c = code.strip().upper()
    # some hospitals label CPT numbers as HCPCS (Level I is CPT)
    if system == "HCPCS" and c.isdigit():
        system = "CPT"
    if system == "CPT":
        if c.endswith("U"):
            return "lab"
        if not c.isdigit():
            return "other"
        n = int(c)
        for lo, hi, grp in _CPT_SECTIONS:
            if lo <= n <= hi:
                return grp
        return "other"
    if system == "HCPCS" and c:
        if c[0] == "C" and c[1:2] in ("1", "2"):
            return "supply"  # C1000-C2999: devices
        if c[:3] == "C89":
            return "imaging"  # C8900-C8999: MRA and other imaging
        return _HCPCS_LETTER.get(c[0], "other")
    return "other"


_MOJIBAKE = re.compile("[ÃÂâ][\u0080-ÿ€-™]")
_KEEP_UPPER = frozenset(
    {
        "MRI",
        "CT",
        "PET",
        "EKG",
        "ECG",
        "EEG",
        "IV",
        "IM",
        "ER",
        "ED",
        "ICU",
        "NICU",
        "OB",
        "GYN",
        "ACL",
        "MCL",
        "COVID",
        "HIV",
        "PSA",
        "TSH",
        "CBC",
        "CMP",
        "BMP",
        "DNA",
        "RNA",
        "EGD",
        "ERCP",
        "MRA",
        "CTA",
        "US",
        "DEXA",
        "D&C",
        "VBAC",
        "PT",
        "OT",
        "ENT",
        "HC",
        "HCG",
        "UA",
        "MCC",
        "CC",
        "OR",
        "DRG",
        "APR",
        "MS",
        "ECMO",
    }
)


def clean_wording(raw: str | None) -> str | None:
    """A hospital's wording, readable: broken accents repaired where possible
    ("Maternity Ã» C-Section"), stray symbols dropped, ALL CAPS put in
    sentence case (keeping common abbreviations such as MRI). Words are never
    changed or dropped."""
    if raw is None:
        return None
    s = " ".join(raw.split())
    if _MOJIBAKE.search(s):
        for enc in ("cp1252", "latin-1"):
            try:
                fixed = s.encode(enc).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            s = fixed
            break
        # whatever is still broken is a symbol, not a word
        s = re.sub("[ÃÂ][\u0080-ÿ]?|[\u0080-\u009f]|�", " - ", s)
        # a lone accented letter between words was a dash or bullet
        s = re.sub(r"(?<=\s)[^\x00-\x7f](?=\s)", "-", s)
        s = re.sub(r"(\s*-\s*){2,}", " - ", s)
        s = " ".join(s.split())
    letters = [ch for ch in s if ch.isalpha()]
    # more than 4 in 5 letters are capitals: written in ALL CAPS
    if letters and sum(ch.isupper() for ch in letters) * 5 > len(letters) * 4:
        words = []
        for w in s.split(" "):
            bare = re.sub(r"[^A-Za-z&]", "", w)
            words.append(w if bare in _KEEP_UPPER else w.lower())
        s = " ".join(words)
        s = s[:1].upper() + s[1:]
    return s or None


# Short forms common in hospital price files, written out for the name we
# show; the hospital's own wording is still shown beside it, labeled.
_SHORT = (
    (r"\bw/o\b", "without"),
    (r"\bw/", "with "),
    (r"\banes(th)?\b", "anesthesia"),
    (r"\bneuraxl\b", "neuraxial"),
    (r"\blbr\b", "labor"),
    (r"\bvag\b", "vaginal"),
    (r"\b(dlvr|deliv|del)\b", "delivery"),
    (r"\bcsec\b", "C-section"),
    (r"\bproc\b", "procedure"),
    (r"\bxr\b", "X-ray"),
    (r"\bcntrst\b", "contrast"),
    (r"\binj\b", "injection"),
    (r"\bnb\b", "newborn"),
    (r"\bhc\s+", ""),  # "HC" = hospital charge: a prefix, not a word of the name
)


def plain_wording(wording: str) -> str:
    """A hospital's wording with its common short forms written out."""
    out = wording
    for pattern, words in _SHORT:
        out = re.sub(pattern, words, out, flags=re.IGNORECASE)
    out = " ".join(out.split())
    return out[:1].upper() + out[1:] if out else wording


@dataclass(frozen=True, slots=True)
class CodeOption:
    code_system: str
    code: str
    name: str  # our plain name (an approved service or a written-out MS-DRG title) or the wording
    wording: str | None  # the hospitals' own wording (or the official title) when name differs
    places: int  # places that published a price for it
    prices: int
    group: str
    service_slug: str | None = None  # the approved service this code belongs to
    service_unit: str | None = None
    core: bool = False  # one of the codes that ARE the thing searched (CODE_RANGES)


def _alternatives(normalized: str) -> list[list[str]]:
    """The word groups to look for: what was typed, plus widened words."""
    typed = [w for w in _WORD.findall(normalized) if w not in _STOP]
    alts: list[list[str]] = []
    if typed:
        alts.append([w + "*" if len(w) >= 3 else w for w in typed])
    padded = f" {normalized.replace('-', ' ')} "
    for key, extra in WIDEN.items():
        k = key.rstrip("*").replace("-", " ")
        hit = (f" {k}" in padded) if key.endswith("*") else (f" {k} " in padded)
        if not hit:
            continue
        for phrase in extra:
            words = _WORD.findall(phrase.rstrip("*").lower())
            if not words:
                continue
            if phrase.endswith("*"):
                words[-1] += "*"
            alts.append(words)
    out: list[list[str]] = []
    for a in alts:
        if a not in out:
            out.append(a)
    return out[:30]


def _merge_spellings(
    found: dict[tuple[str, str], tuple[str | None, int, int]],
) -> dict[tuple[str, str], tuple[str | None, int, int]]:
    """One option per CPT number however hospitals wrote it (D-065): "1967",
    "01967", or labeled HCPCS. The option uses the standard spelling (CPT,
    five digits) when it was published; searching it finds every spelling.
    Places is the largest count among the spellings (never added together, so
    it can't overstate)."""
    groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for sys_, code in found:
        c = code.strip()
        if sys_ in ("CPT", "HCPCS") and c.isdigit() and len(c) <= 5:
            canon = ("CPT", c.zfill(5))
        else:
            canon = (sys_, code)
        groups.setdefault(canon, []).append((sys_, code))
    out: dict[tuple[str, str], tuple[str | None, int, int]] = {}
    for canon, spellings in groups.items():
        best = max(spellings, key=lambda k: (k == canon, found[k][1], found[k][2]))
        wording = next(
            (found[k][0] for k in sorted(spellings, key=lambda k: -found[k][1]) if found[k][0]),
            None,
        )
        places = max(found[k][1] for k in spellings)
        prices = max(found[k][2] for k in spellings)
        out[best] = (wording, places, prices)
    return out


def _ranges_for(normalized: str) -> list[tuple[str, int, int]]:
    padded = f" {normalized.replace('-', ' ')} "
    out: list[tuple[str, int, int]] = []
    for key, ranges in CODE_RANGES.items():
        if f" {key.replace('-', ' ')} " in padded:
            out.extend(r for r in ranges if r not in out)
    return out


def _tsquery(alts: list[list[str]]) -> str:
    def term(w: str) -> str:
        return w[:-1] + ":*" if w.endswith("*") else w

    parts = []
    for i, a in enumerate(alts):
        # every word, in any order ("arthroplasty knee"); a phrase with a
        # one- or two-letter word ("c section") must be in order
        tight = i > 0 and any(len(w.rstrip("*")) <= 2 for w in a)
        inner = (" <-> " if tight else " & ").join(term(w) for w in a)
        parts.append(f"({inner})" if len(a) > 1 else inner)
    return " | ".join(parts)


def _negated_only(wording: str, words: list[str]) -> bool:
    """True when every mention of the words is "without ..." / "no ..."."""
    low = wording.lower()
    found = False
    for w in words:
        stem = w.rstrip("*")
        for m in re.finditer(rf"\b{re.escape(stem)}", low):
            found = True
            before = low[max(0, m.start() - 20) : m.start()]
            if not re.search(r"\b(without|w/o|wo|no|non)\s+(general\s+)?$", before):
                return False
    return found


def find_options(conn: Connection, query: str, limit: int = 400) -> list[CodeOption]:
    """Every published code option for the words typed, best known first."""
    from .code_names import drg_plain
    from .matching import normalize_name

    q = normalize_name(query)
    if len(q) < 2 or len(q) > 60:
        return []
    n = max(1, min(limit, 600))
    alts = _alternatives(q)
    found: dict[tuple[str, str], tuple[str | None, int, int]] = {}
    if alts:
        tsq = _tsquery(alts)
        for sys_, code, wording, places, prices in conn.execute(
            text(
                """
                SELECT system::text, code, hospital_description, facilities, prices
                FROM ref.code_index
                WHERE to_tsvector('english', coalesce(hospital_description, ''))
                      @@ to_tsquery('english', :tsq)
                ORDER BY facilities DESC, prices DESC, system, code
                LIMIT :n
                """
            ),
            {"tsq": tsq, "n": n},
        ).all():
            found[(str(sys_), str(code))] = (wording, int(places), int(prices))
        # official public titles (MS-DRG, HCPCS) of codes hospitals published
        for sys_, code, wording, places, prices in conn.execute(
            text(
                """
                SELECT i.system::text, i.code, i.hospital_description, i.facilities, i.prices
                FROM ref.code c
                JOIN ref.code_index i ON i.system = c.system AND i.code = c.code
                WHERE c.system IN ('MS-DRG', 'HCPCS') AND c.descriptor IS NOT NULL
                  AND to_tsvector('english', c.descriptor) @@ to_tsquery('english', :tsq)
                GROUP BY i.system, i.code, i.hospital_description, i.facilities, i.prices
                ORDER BY i.facilities DESC
                LIMIT :n
                """
            ),
            {"tsq": tsq, "n": n},
        ).all():
            found.setdefault((str(sys_), str(code)), (wording, int(places), int(prices)))
    anesthesia = any(a[0].startswith(("anesth", "anaesth")) for a in alts)
    for sys_, lo, hi in _ranges_for(q):
        # codes published without leading zeros ("1967") count too
        for rsys, code, wording, places, prices in conn.execute(
            text(
                """
                SELECT system::text, code, hospital_description, facilities, prices
                FROM ref.code_index
                WHERE system = CAST(:sys AS ref.code_system)
                  AND (CASE WHEN code ~ '^[0-9]{3,5}$' THEN code::int END)
                      BETWEEN :lo AND :hi
                ORDER BY facilities DESC, prices DESC, code
                LIMIT :n
                """
            ),
            {"sys": sys_, "lo": lo, "hi": hi, "n": n},
        ).all():
            found.setdefault((str(rsys), str(code)), (wording, int(places), int(prices)))
    if not found:
        return []
    found = _merge_spellings(found)
    keys = list(found)
    pairs = [f"{s}:{c}" for s, c in keys]
    services = {
        str(x[0]): (str(x[1]), str(x[2]), str(x[3]))
        for x in conn.execute(
            text(
                """
                SELECT DISTINCT ON (pc.code_system::text || ':' || pc.code)
                       pc.code_system::text || ':' || pc.code, p.slug, p.consumer_name,
                       p.unit
                FROM ref.procedure_code pc JOIN ref.procedure p ON p.id = pc.procedure_id
                WHERE pc.review_state = 'approved' AND p.review_state = 'approved'
                  AND p.kind = 'service' AND p.slug IS NOT NULL
                  AND pc.code_system::text || ':' || pc.code = ANY(:pairs)
                ORDER BY pc.code_system::text || ':' || pc.code, p.consumer_name
                """
            ),
            {"pairs": pairs},
        ).all()
    }
    titles = {
        (str(x[0]), str(x[1])): str(x[2])
        for x in conn.execute(
            text(
                """
                SELECT DISTINCT ON (system, code) system::text, code, descriptor FROM ref.code
                WHERE system IN ('MS-DRG', 'HCPCS') AND descriptor IS NOT NULL
                  AND system::text || ':' || code = ANY(:pairs)
                ORDER BY system, code, version DESC
                """
            ),
            {"pairs": pairs},
        ).all()
    }
    typed_words = alts[0] if alts else []
    out: list[CodeOption] = []
    for (sys_, code), (raw, places, prices) in found.items():
        wording = clean_wording(raw)
        title = titles.get((sys_, code))
        # "without anesthesia" is not an anesthesia option
        if anesthesia and wording and not (sys_ == "CPT" and group_for(sys_, code) == "anesthesia"):
            if _negated_only(wording, ["anesth", "anaesth"]) and not title:
                continue
        elif typed_words and wording and not title and _negated_only(wording, typed_words):
            continue
        slug, service_name, unit = services.get(f"{sys_}:{code}", (None, None, None))
        if service_name:
            name, shown = service_name, wording or (clean_wording(title) if title else None)
        elif title and sys_ == "MS-DRG":
            name, shown = drg_plain(title), wording
        elif title:
            name, shown = clean_wording(title) or title, wording
        elif wording and group_for(sys_, code) == "stay":
            # hospital-stay wording uses the DRG abbreviations: write them out
            name, shown = drg_plain(wording), wording
        elif wording and plain_wording(wording) != wording:
            name, shown = plain_wording(wording), wording
        else:
            name, shown = wording or f"{sys_} {code}", None
        if shown and shown.lower() == name.lower():
            shown = None
        out.append(
            CodeOption(sys_, code, name, shown, places, prices, group_for(sys_, code), slug, unit)
        )
    order = {g: i for i, g in enumerate(GROUPS)}
    ranges = _ranges_for(q)

    def core(o: CodeOption) -> int:
        """0 when the code is one of the codes that ARE the thing (e.g. a
        birth's own stays), so those come first in their group."""
        c = o.code.strip()
        system = "CPT" if o.code_system == "HCPCS" and c.isdigit() else o.code_system
        if c.isdigit():
            n_ = int(c)
            if any(system == rs and lo <= n_ <= hi for rs, lo, hi in ranges):
                return 0
        return 1

    out = [replace(o, core=core(o) == 0) for o in out]
    out.sort(key=lambda o: (order[o.group], core(o), -o.places, -o.prices, o.code_system, o.code))
    return out[:n]
