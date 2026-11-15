"""Code numbers that ARE a common procedure, whatever a hospital wrote for them
(Cooper, 2026-11-14: "these fixes should be for everything and every
procedure"). When a person types one of these words, every published code in
these ranges is listed and comes first in its group; codes found only by
wording come after.

Sources (code numbers only, D-002; D-061):
- MS-DRG numbers: CMS MS-DRG v42 definitions (MDC groupings).
- APR-DRG numbers: 3M APR-DRG groups as hospitals publish them, often with a
  severity digit appended (5601 = group 560, severity 1).
- CPT numbers: the CPT code ranges as published in CMS's physician fee
  schedule files; HCPCS Level II and CDT numbers from CMS and ADA code lists.
No descriptor text is stored here. Each option still shows its own wording,
so a code that doesn't fit is visible, never hidden behind our name.
(Claude, delegated by Cooper, D-061)
"""

from __future__ import annotations

import re

Range = tuple[str, str, str]  # (code system, first code, last code)


def _r(system: str, first: str, last: str | None = None) -> Range:
    return (system, first, last or first)


BIRTH: tuple[Range, ...] = (
    _r("MS-DRG", "768"),
    _r("MS-DRG", "783", "798"),
    _r("MS-DRG", "805", "807"),
    _r("APR-DRG", "540", "566"),
    _r("APR-DRG", "580", "640"),
    _r("APR-DRG", "5400", "5664"),
    _r("APR-DRG", "5800", "6404"),
    _r("CPT", "59000", "59899"),
    _r("CPT", "01958", "01969"),
)
C_SECTION = (_r("MS-DRG", "783", "788"), _r("CPT", "59510", "59622"), _r("CPT", "01961", "01963"))
NEWBORN = (_r("MS-DRG", "789", "795"), _r("APR-DRG", "580", "640"), _r("APR-DRG", "5800", "6404"))
ANESTHESIA = (_r("CPT", "00100", "01999"),)
KNEE_REPLACEMENT = (
    _r("MS-DRG", "469", "470"),
    _r("MS-DRG", "461", "462"),
    _r("CPT", "27447"),
    _r("CPT", "27486", "27487"),
    _r("CPT", "01402"),
)
HIP_REPLACEMENT = (
    _r("MS-DRG", "469", "470"),
    _r("MS-DRG", "461", "462"),
    _r("CPT", "27130"),
    _r("CPT", "27132", "27138"),
    _r("CPT", "01214"),
)
KNEE_SCOPE = (_r("CPT", "29866", "29889"), _r("CPT", "01382"))
KNEE_IMAGING = (_r("CPT", "73560", "73565"), _r("CPT", "73721", "73723"))
SHOULDER = (
    _r("CPT", "29805", "29828"),
    _r("CPT", "23410", "23430"),
    _r("CPT", "23472", "23474"),
    _r("CPT", "73020", "73030"),
    _r("CPT", "73221", "73223"),
)
SPINE_FUSION = (_r("MS-DRG", "453", "460"), _r("MS-DRG", "471", "473"), _r("CPT", "22551", "22865"))
BACK_IMAGING = (
    _r("CPT", "72020", "72120"),
    _r("CPT", "72125", "72133"),
    _r("CPT", "72141", "72159"),
)
COLONOSCOPY = (
    _r("CPT", "45378", "45398"),
    _r("HCPCS", "G0105"),
    _r("HCPCS", "G0121"),
    _r("CPT", "00811", "00813"),
)
ENDOSCOPY = (_r("CPT", "43235", "43259"), _r("CPT", "00731", "00732"))
CATARACT = (_r("CPT", "66982", "66984"), _r("CPT", "66987", "66991"), _r("CPT", "00142"))
MRI = (
    _r("CPT", "70336"),
    _r("CPT", "70540", "70559"),
    _r("CPT", "71550", "71552"),
    _r("CPT", "72141", "72159"),
    _r("CPT", "72195", "72198"),
    _r("CPT", "73218", "73225"),
    _r("CPT", "73718", "73725"),
    _r("CPT", "74181", "74185"),
    _r("CPT", "77046", "77049"),
)
CT = (
    _r("CPT", "70450", "70498"),
    _r("CPT", "71250", "71275"),
    _r("CPT", "72125", "72133"),
    _r("CPT", "72191", "72194"),
    _r("CPT", "73200", "73206"),
    _r("CPT", "73700", "73706"),
    _r("CPT", "74150", "74178"),
    _r("CPT", "74261", "74263"),
)
XRAY = (
    _r("CPT", "70100", "70370"),
    _r("CPT", "71045", "71048"),
    _r("CPT", "72020", "72220"),
    _r("CPT", "73000", "73140"),
    _r("CPT", "73501", "73660"),
    _r("CPT", "74018", "74022"),
)
MAMMOGRAM = (_r("CPT", "77065", "77067"),)
ULTRASOUND = (
    _r("CPT", "76536"),
    _r("CPT", "76604"),
    _r("CPT", "76641", "76642"),
    _r("CPT", "76700", "76776"),
    _r("CPT", "76801", "76857"),
    _r("CPT", "76870", "76873"),
    _r("CPT", "93880", "93882"),
    _r("CPT", "93925", "93931"),
    _r("CPT", "93970", "93971"),
)
PREGNANCY_ULTRASOUND = (_r("CPT", "76801", "76828"),)
HEART_TESTS = (
    _r("CPT", "93000", "93010"),
    _r("CPT", "93015", "93018"),
    _r("CPT", "93303", "93355"),
)
HEART_CATH = (_r("CPT", "93451", "93533"), _r("CPT", "92928", "92944"))
HEART_ATTACK = (_r("MS-DRG", "280", "285"), _r("APR-DRG", "190"), _r("APR-DRG", "1901", "1904"))
HEART_FAILURE = (_r("MS-DRG", "291", "293"), _r("APR-DRG", "194"), _r("APR-DRG", "1941", "1944"))
BYPASS = (_r("MS-DRG", "231", "236"), _r("CPT", "33510", "33536"))
PACEMAKER = (_r("MS-DRG", "242", "244"), _r("CPT", "33206", "33249"))
STROKE = (
    _r("MS-DRG", "064", "066"),
    _r("MS-DRG", "64", "66"),
    _r("APR-DRG", "045"),
    _r("APR-DRG", "0451", "0454"),
)
PNEUMONIA = (_r("MS-DRG", "193", "195"), _r("APR-DRG", "139"), _r("APR-DRG", "1391", "1394"))
SEPSIS = (_r("MS-DRG", "870", "872"), _r("APR-DRG", "720"), _r("APR-DRG", "7201", "7204"))
COPD = (_r("MS-DRG", "190", "192"),)
KIDNEY_FAILURE = (_r("MS-DRG", "682", "684"),)
APPENDIX = (_r("MS-DRG", "338", "343"), _r("CPT", "44950", "44979"))
GALLBLADDER = (_r("MS-DRG", "411", "419"), _r("CPT", "47562", "47564"), _r("CPT", "47600", "47620"))
HERNIA = (_r("CPT", "49591", "49659"), _r("MS-DRG", "353", "355"))
TONSILS = (_r("CPT", "42820", "42836"),)
HYSTERECTOMY = (
    _r("MS-DRG", "742", "743"),
    _r("CPT", "58150", "58294"),
    _r("CPT", "58541", "58573"),
)
TUBES_TIED = (
    _r("CPT", "58600", "58615"),
    _r("CPT", "58670", "58671"),
    _r("MS-DRG", "796", "798"),
    _r("MS-DRG", "767"),
)
VASECTOMY = (_r("CPT", "55250"),)
CARPAL_TUNNEL = (_r("CPT", "64721"), _r("CPT", "29848"))
BARIATRIC = (_r("MS-DRG", "619", "621"), _r("CPT", "43644", "43645"), _r("CPT", "43770", "43775"))
ER_VISIT = (_r("CPT", "99281", "99285"), _r("HCPCS", "G0380", "G0384"))
OFFICE_VISIT = (_r("CPT", "99202", "99215"),)
PREVENTIVE = (_r("CPT", "99381", "99397"), _r("HCPCS", "G0438", "G0439"), _r("HCPCS", "G0402"))
PHYSICAL_THERAPY = (_r("CPT", "97110", "97164"), _r("CPT", "97530"), _r("CPT", "97140"))
OCCUPATIONAL_THERAPY = (_r("CPT", "97165", "97168"),)
SPEECH_THERAPY = (_r("CPT", "92507"), _r("CPT", "92521", "92524"))
SLEEP_STUDY = (_r("CPT", "95800", "95811"),)
DIALYSIS = (_r("CPT", "90935", "90947"),)
FLU_SHOT = (
    _r("CPT", "90653", "90694"),
    _r("CPT", "90630"),
    _r("HCPCS", "G0008"),
    _r("HCPCS", "Q2034", "Q2039"),
)
VACCINE_ADMIN = (_r("CPT", "90460", "90474"), _r("HCPCS", "G0008", "G0010"))
VACCINES = (_r("CPT", "90476", "90759"), *VACCINE_ADMIN)
CHEMO = (_r("CPT", "96401", "96549"),)
BLOOD_TESTS = (
    _r("CPT", "80047", "80053"),
    _r("CPT", "80061"),
    _r("CPT", "83036"),
    _r("CPT", "84443"),
    _r("CPT", "85025", "85027"),
    _r("CPT", "84153"),
    _r("CPT", "82306"),
)
URINE_TEST = (_r("CPT", "81000", "81003"),)
PAP = (
    _r("CPT", "88141", "88175"),
    _r("HCPCS", "P3000", "P3001"),
    _r("HCPCS", "Q0091"),
    _r("HCPCS", "G0101"),
    _r("HCPCS", "G0123", "G0124"),
)
STD_TESTS = (
    _r("CPT", "87491"),
    _r("CPT", "87591"),
    _r("CPT", "87661"),
    _r("CPT", "86701", "86703"),
    _r("CPT", "87389"),
    _r("CPT", "86592", "86593"),
    _r("CPT", "86780"),
    _r("CPT", "86695", "86696"),
    _r("CPT", "86803"),
    _r("CPT", "87340"),
)
EYE_EXAM = (_r("CPT", "92002", "92015"),)
ALLERGY_TESTS = (_r("CPT", "95004", "95078"),)
PREGNANCY_TEST = (_r("CPT", "81025"), _r("CPT", "84702", "84703"))
STREP_TEST = (_r("CPT", "87880"), _r("CPT", "87651"))
FLU_TEST = (_r("CPT", "87804"), _r("CPT", "87502"), _r("CPT", "87400"))
COVID_TEST = (_r("CPT", "87635"), _r("CPT", "87426"), _r("CPT", "87811"), _r("CPT", "86769"))
DENTAL_CLEANING = (_r("CDT", "D1110", "D1120"), _r("HCPCS", "D1110", "D1120"))
DENTAL_EXAM = (_r("CDT", "D0120", "D0180"), _r("HCPCS", "D0120", "D0180"))
DENTAL_XRAY = (_r("CDT", "D0210", "D0350"), _r("HCPCS", "D0210", "D0350"))
FILLING = (_r("CDT", "D2140", "D2394"), _r("HCPCS", "D2140", "D2394"))
CROWN = (_r("CDT", "D2740", "D2799"), _r("HCPCS", "D2740", "D2799"))
ROOT_CANAL = (_r("CDT", "D3310", "D3348"), _r("HCPCS", "D3310", "D3348"))
EXTRACTION = (_r("CDT", "D7140", "D7250"), _r("HCPCS", "D7140", "D7250"))
IMPLANT = (_r("CDT", "D6010", "D6067"), _r("HCPCS", "D6010", "D6067"))

# what people type -> the ranges (a word matches anywhere in the search)
CODE_RANGES: dict[str, tuple[Range, ...]] = {
    "birth": BIRTH,
    "childbirth": BIRTH,
    "baby": BIRTH,
    "having a baby": BIRTH,
    "labor": BIRTH,
    "delivery": BIRTH,
    "pregnancy": BIRTH + PREGNANCY_ULTRASOUND,
    "pregnant": BIRTH + PREGNANCY_ULTRASOUND,
    "c section": C_SECTION,
    "c-section": C_SECTION,
    "csection": C_SECTION,
    "cesarean": C_SECTION,
    "caesarean": C_SECTION,
    "newborn": NEWBORN,
    "anesthesia": ANESTHESIA,
    "anesthetic": ANESTHESIA,
    "anaesthesia": ANESTHESIA,
    "epidural": (_r("CPT", "01967", "01969"), _r("CPT", "62320", "62327")),
    "knee replacement": KNEE_REPLACEMENT,
    "hip replacement": HIP_REPLACEMENT,
    "joint replacement": KNEE_REPLACEMENT + HIP_REPLACEMENT,
    "knee": KNEE_REPLACEMENT + KNEE_SCOPE + KNEE_IMAGING,
    "hip": (*HIP_REPLACEMENT, _r("CPT", "73501", "73523"), _r("CPT", "73721", "73723")),
    "acl": (_r("CPT", "29888"),),
    "meniscus": (_r("CPT", "29880", "29883"),),
    "arthroscopy": (*KNEE_SCOPE, _r("CPT", "29805", "29828")),
    "shoulder": SHOULDER,
    "spinal fusion": SPINE_FUSION,
    "back surgery": (*SPINE_FUSION, _r("CPT", "63030", "63048")),
    "back": BACK_IMAGING + SPINE_FUSION,
    "spine": BACK_IMAGING + SPINE_FUSION,
    "colonoscopy": COLONOSCOPY,
    "endoscopy": ENDOSCOPY,
    "egd": ENDOSCOPY,
    "cataract": CATARACT,
    "mri": MRI,
    "ct": CT,
    "cat scan": CT,
    "ct scan": CT,
    "x-ray": XRAY,
    "xray": XRAY,
    "x ray": XRAY,
    "mammogram": MAMMOGRAM,
    "ultrasound": ULTRASOUND,
    "sonogram": ULTRASOUND,
    "echocardiogram": (_r("CPT", "93303", "93355"),),
    "echo": (_r("CPT", "93303", "93355"),),
    "ekg": (_r("CPT", "93000", "93010"),),
    "ecg": (_r("CPT", "93000", "93010"),),
    "stress test": (_r("CPT", "93015", "93018"),),
    "heart": HEART_TESTS + HEART_CATH + HEART_ATTACK + HEART_FAILURE + BYPASS + PACEMAKER,
    "heart attack": HEART_ATTACK + HEART_CATH,
    "heart failure": HEART_FAILURE,
    "stent": HEART_CATH,
    "heart cath": HEART_CATH,
    "bypass": BYPASS,
    "pacemaker": PACEMAKER,
    "stroke": STROKE,
    "pneumonia": PNEUMONIA,
    "sepsis": SEPSIS,
    "copd": COPD,
    "kidney failure": KIDNEY_FAILURE,
    "appendix": APPENDIX,
    "appendectomy": APPENDIX,
    "gallbladder": GALLBLADDER,
    "hernia": HERNIA,
    "tonsils": TONSILS,
    "tonsillectomy": TONSILS,
    "hysterectomy": HYSTERECTOMY,
    "tubes tied": TUBES_TIED,
    "tubal": TUBES_TIED,
    "vasectomy": VASECTOMY,
    "carpal tunnel": CARPAL_TUNNEL,
    "weight loss surgery": BARIATRIC,
    "gastric bypass": BARIATRIC,
    "gastric sleeve": BARIATRIC,
    "bariatric": BARIATRIC,
    "emergency": ER_VISIT,
    "er": ER_VISIT,
    "emergency room": ER_VISIT,
    "office visit": OFFICE_VISIT,
    "doctor visit": OFFICE_VISIT,
    "checkup": (*PREVENTIVE, *OFFICE_VISIT),
    "check up": (*PREVENTIVE, *OFFICE_VISIT),
    "physical": PREVENTIVE,
    "annual": PREVENTIVE,
    "wellness": PREVENTIVE,
    "well child": (_r("CPT", "99381", "99384"), _r("CPT", "99391", "99394")),
    "well baby": (_r("CPT", "99381"), _r("CPT", "99391")),
    "physical therapy": PHYSICAL_THERAPY,
    "occupational therapy": OCCUPATIONAL_THERAPY,
    "speech therapy": SPEECH_THERAPY,
    "sleep study": SLEEP_STUDY,
    "dialysis": DIALYSIS,
    "flu shot": FLU_SHOT,
    "flu vaccine": FLU_SHOT,
    "flu": FLU_SHOT,
    "vaccine": VACCINES,
    "vaccines": VACCINES,
    "shot": VACCINES,
    "shots": VACCINES,
    "immunization": VACCINES,
    "shingles": (_r("CPT", "90750"), _r("CPT", "90736")),
    "tetanus": (_r("CPT", "90714", "90715"), _r("CPT", "90702"), _r("CPT", "90700")),
    "tdap": (_r("CPT", "90715"),),
    "hpv": (_r("CPT", "90649", "90651"),),
    "pneumonia vaccine": (
        _r("CPT", "90670"),
        _r("CPT", "90671"),
        _r("CPT", "90677"),
        _r("CPT", "90732"),
    ),
    "chemo": CHEMO,
    "chemotherapy": CHEMO,
    "blood test": BLOOD_TESTS,
    "blood work": BLOOD_TESTS,
    "lab": BLOOD_TESTS + URINE_TEST,
    "urine": URINE_TEST,
    "pap": PAP,
    "pap smear": PAP,
    "pap test": PAP,
    "std": STD_TESTS,
    "sti": STD_TESTS,
    "std test": STD_TESTS,
    "hiv test": (_r("CPT", "86701", "86703"), _r("CPT", "87389")),
    "eye exam": EYE_EXAM,
    "vision exam": EYE_EXAM,
    "allergy": ALLERGY_TESTS,
    "allergy test": ALLERGY_TESTS,
    "pregnancy test": PREGNANCY_TEST,
    "strep": STREP_TEST,
    "strep test": STREP_TEST,
    "flu test": FLU_TEST,
    "covid test": COVID_TEST,
    "teeth cleaning": DENTAL_CLEANING,
    "dental cleaning": DENTAL_CLEANING,
    "cleaning": DENTAL_CLEANING,
    "dental exam": DENTAL_EXAM,
    "dental": DENTAL_CLEANING
    + DENTAL_EXAM
    + DENTAL_XRAY
    + FILLING
    + CROWN
    + ROOT_CANAL
    + EXTRACTION,
    "dentist": DENTAL_CLEANING
    + DENTAL_EXAM
    + DENTAL_XRAY
    + FILLING
    + CROWN
    + ROOT_CANAL
    + EXTRACTION,
    "filling": FILLING,
    "crown": CROWN,
    "root canal": ROOT_CANAL,
    "tooth extraction": EXTRACTION,
    "extraction": EXTRACTION,
    "wisdom teeth": (_r("CDT", "D7220", "D7250"), _r("HCPCS", "D7220", "D7250")),
    "implant": IMPLANT,
}

_CODE = re.compile(r"^([A-Z]?)(\d{1,5})$")


def split_code(code: str) -> tuple[str, int] | None:
    """("G", 105) for "G0105", ("", 1967) for "01967" or "1967"."""
    m = _CODE.match(code.strip().upper())
    return (m.group(1), int(m.group(2))) if m else None


def in_range(system: str, code: str, r: Range) -> bool:
    """Whether a code is in a range; CPT numbers labeled HCPCS count as CPT,
    and missing leading zeros don't matter."""
    rs, first, last = r
    parts = split_code(code)
    lo, hi = split_code(first), split_code(last)
    if parts is None or lo is None or hi is None:
        return False
    sys_ = "CPT" if system == "HCPCS" and not parts[0] else system
    return sys_ == rs and parts[0] == lo[0] == hi[0] and lo[1] <= parts[1] <= hi[1]


def string_ranges(r: Range) -> list[tuple[list[str], str, str, int]]:
    """A range as (code systems, first, last, length) text ranges that the
    code index can look up directly: the same length and digits compare the
    same way as numbers. CPT numbers come both as five digits ("01967") and
    without leading zeros ("1967"), also labeled HCPCS; MS-DRG as "064" or
    "64"; letter codes (G0105, D1110) are a letter and four digits."""
    rs, first, last = r
    lo, hi = split_code(first), split_code(last)
    if lo is None or hi is None or lo[0] != hi[0] or lo[1] > hi[1]:
        return []
    letter = lo[0]
    systems = ["CPT", "HCPCS"] if rs == "CPT" else [rs]
    if letter:
        return [(systems, f"{letter}{lo[1]:04d}", f"{letter}{hi[1]:04d}", 5)]
    pad = {"CPT": 5, "MS-DRG": 3}.get(rs, 0)
    out: list[tuple[list[str], str, str, int]] = []
    for length in range(len(str(lo[1])), len(str(hi[1])) + 1):
        a = max(lo[1], 10 ** (length - 1))
        b = min(hi[1], 10**length - 1)
        if a <= b:
            out.append((systems, str(a), str(b), length))
    if pad and len(str(lo[1])) < pad:
        b = min(hi[1], 10 ** (pad - 1) - 1)  # padded forms of numbers shorter than pad
        out.append((systems, str(lo[1]).zfill(pad), str(b).zfill(pad), pad))
    return out


def ranges_for(normalized: str) -> list[Range]:
    """Every range for the words in a search. A word inside a longer matched
    phrase doesn't count on its own ("physical" in "physical therapy")."""
    padded = f" {normalized.replace('-', ' ')} "
    hits = [k for k in CODE_RANGES if f" {k.replace('-', ' ')} " in padded]
    spaced = {k: f" {k.replace('-', ' ')} " for k in hits}
    keep = [
        k for k in hits if not any(spaced[k] != spaced[o] and spaced[k] in spaced[o] for o in hits)
    ]
    out: list[Range] = []
    for key in keep:
        out.extend(r for r in CODE_RANGES[key] if r not in out)
    return out
