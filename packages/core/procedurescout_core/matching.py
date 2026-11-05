"""Payer/plan name matching guards.

Raw names from hospital files are only ever matched to a canonical payer by
an exact lookup of their normalized text in an approved alias row. There is
no fuzzy matching and no automatic merging: "Anthem Blue Cross Blue Shield"
and "BCBS BlueCard" stay separate until a person approves a mapping.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s&+/-]", flags=re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Lookup key for a raw payer or plan name.

    Only removes differences that cannot change meaning: letter case,
    accents/width forms, surrounding and repeated whitespace, and stray
    punctuation such as periods and commas. Words are never dropped or
    reordered, so distinct names keep distinct keys.
    """
    text = unicodedata.normalize("NFKC", raw).casefold()
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()
