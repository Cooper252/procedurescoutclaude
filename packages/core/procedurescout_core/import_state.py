"""Import-run state machine.

The same transition list is seeded into src.import_transition by migration
0001 and enforced there by a trigger, so a bad transition fails both in
Python and in the database. tests/test_state_machine.py checks they agree.
"""

from __future__ import annotations

from .enums import ImportState as S

# States in which work is in progress; any of them may fail.
_WORKING: tuple[S, ...] = (
    S.QUEUED,
    S.DOWNLOADING,
    S.DOWNLOADED,
    S.VALIDATING,
    S.PARSING,
    S.NORMALIZING,
    S.LOADING,
    S.QUALITY_REVIEW,
)

ALLOWED_TRANSITIONS: frozenset[tuple[S, S]] = frozenset(
    {
        (S.DISCOVERED, S.QUEUED),
        (S.QUEUED, S.DOWNLOADING),
        (S.DOWNLOADING, S.DOWNLOADED),
        (S.DOWNLOADED, S.VALIDATING),
        # Same file hash as the last published run: nothing new to import.
        (S.DOWNLOADED, S.RETIRED),
        (S.VALIDATING, S.PARSING),
        (S.PARSING, S.NORMALIZING),
        (S.NORMALIZING, S.LOADING),
        (S.LOADING, S.QUALITY_REVIEW),
        (S.QUALITY_REVIEW, S.PUBLISHED),
        (S.PUBLISHED, S.STALE),
        (S.PUBLISHED, S.RETIRED),
        (S.STALE, S.PUBLISHED),  # source re-checked and confirmed current
        (S.STALE, S.RETIRED),
        (S.FAILED, S.QUEUED),  # retry from the last checkpoint
        (S.FAILED, S.RETIRED),
        *((working, S.FAILED) for working in _WORKING),
    }
)


class IllegalTransitionError(ValueError):
    """Raised for a state change the import pipeline does not allow."""


def can_transition(current: S, target: S) -> bool:
    return (current, target) in ALLOWED_TRANSITIONS


def transition(current: S, target: S) -> S:
    """Return the target state, or raise if the move is not allowed."""
    if not can_transition(current, target):
        raise IllegalTransitionError(f"import run cannot move from {current} to {target}")
    return target
