"""Plain-English names for billing codes in search suggestions (Cooper,
2026-11-12: "vaginal delivery without sterilization or D&C without CC/MCC ... I
don't know what that means").

- A code that belongs to one of our approved services gets that service's name.
- An MS-DRG title (CMS, public) has its abbreviations written out: "W/O CC/MCC"
  becomes "without complications", "O.R." becomes "operating room", and so on.
  Words are only expanded, never dropped, so the meaning stays CMS's.
- Anything else keeps the hospitals' wording, labeled as theirs by the site.
CPT descriptor text is never used (D-002).
"""

from __future__ import annotations

import re

# longest first, so "W/O CC/MCC" is replaced before "W/O"
_DRG_WORDS: tuple[tuple[str, str], ...] = (
    (r"\bW/O CC/MCC\b", "without complications"),
    (r"\bW CC/MCC\b", "with complications"),
    (r"\bW/O MCC\b", "without major complications"),
    (r"\bW/O CC\b", "without complications"),
    (r"\bW MCC\b", "with major complications"),
    (r"\bW CC\b", "with complications"),
    (r"\bW/O\b", "without"),
    (r"\bW\b", "with"),
    (r"\bO\.R\.", "operating room"),
    (r"\bD&C\b", "D&C (a procedure to clear the uterus)"),
    (r"\bPROC\b", "procedure"),
    (r"\bPROCS\b", "procedures"),
    (r"\bDX\b", "diagnosis"),
    (r"\bDXS\b", "diagnoses"),
    (r"\bMV\b", "breathing machine"),
    (r"\bECMO\b", "heart-lung machine (ECMO)"),
    (r"\bSIG\b", "significant"),
    (r"\bMAJ\b", "major"),
    (r"\bEXC\b", "except"),
    (r"\bINF\b", "infection"),
    (r"\bTX\b", "treatment"),
    (r"\bJT\b", "joint"),
    (r"\bLOWER EXTREMITY\b", "leg"),
    (r"\bUPPER EXTREMITY\b", "arm"),
    (r"\bSTERILIZATION\b", "getting tubes tied (sterilization)"),
    (r"\bSEPTICEMIA\b", "blood infection (septicemia)"),
    (r">\s*96 HOURS", "more than 96 hours"),
    (r"<\s*96 HOURS", "less than 96 hours"),
)


def drg_plain(title: str) -> str:
    """An MS-DRG title with its abbreviations written out, in sentence case."""
    out = " ".join(title.split())
    for pattern, words in _DRG_WORDS:
        out = re.sub(pattern, words, out, flags=re.IGNORECASE)
    out = out.lower()
    out = out.replace(
        "d&c (a procedure to clear the uterus)", "D&C (a procedure to clear the uterus)"
    )
    out = out.replace("(ecmo)", "(ECMO)")
    return out[:1].upper() + out[1:] if out else out
