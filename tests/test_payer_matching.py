"""Regression guard for the legacy carrier/plan confusion bugs:
distinct payer names are never merged automatically."""

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from procedurescout_core.matching import normalize_name
from procedurescout_core.payer_repo import record_raw_payer, resolve_payer

ANTHEM = "Anthem Blue Cross Blue Shield"
BLUECARD = "BCBS BlueCard"


def test_normalization_only_removes_cosmetic_differences() -> None:
    assert normalize_name("  ANTHEM  Blue Cross, Blue Shield. ") == normalize_name(ANTHEM)
    assert normalize_name(ANTHEM) != normalize_name(BLUECARD)
    assert normalize_name("Blue Cross Blue Shield") != normalize_name(ANTHEM)
    assert normalize_name("Aetna HMO") != normalize_name("Aetna PPO")


def _approved_payer(conn: Connection, name: str) -> object:
    payer_id = conn.execute(
        text("INSERT INTO ref.payer (canonical_name) VALUES (:n) RETURNING id"), {"n": name}
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO ref.payer_alias (raw_text, raw_normalized, payer_id, match_type, "
            "review_state, reviewed_by, reviewed_at) "
            "VALUES (:r, :k, :p, 'exact', 'approved', 'test-reviewer', now())"
        ),
        {"r": name, "k": normalize_name(name), "p": payer_id},
    )
    return payer_id


def test_anthem_and_bluecard_never_auto_merge(conn: Connection) -> None:
    anthem_id = _approved_payer(conn, ANTHEM)
    assert resolve_payer(conn, "  anthem blue cross blue shield ") == anthem_id
    assert resolve_payer(conn, BLUECARD) is None
    assert resolve_payer(conn, "Blue Cross Blue Shield") is None


def test_unseen_name_recorded_as_unmapped(conn: Connection) -> None:
    record_raw_payer(conn, BLUECARD)
    row = conn.execute(
        text("SELECT payer_id, match_type::text FROM ref.payer_alias WHERE raw_text = :r"),
        {"r": BLUECARD},
    ).one()
    assert row == (None, "unmapped")
    assert resolve_payer(conn, BLUECARD) is None


def test_recording_does_not_overwrite_existing_mapping(conn: Connection) -> None:
    anthem_id = _approved_payer(conn, ANTHEM)
    record_raw_payer(conn, ANTHEM.upper())
    assert resolve_payer(conn, ANTHEM) == anthem_id


def test_proposed_mapping_not_used(conn: Connection) -> None:
    payer_id = conn.execute(
        text("INSERT INTO ref.payer (canonical_name) VALUES ('Anthem') RETURNING id")
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO ref.payer_alias (raw_text, raw_normalized, payer_id, match_type) "
            "VALUES ('Anthem', 'anthem', :p, 'normalized')"
        ),
        {"p": payer_id},
    )
    assert resolve_payer(conn, "Anthem") is None


def test_one_raw_name_cannot_map_to_two_payers(conn: Connection) -> None:
    _approved_payer(conn, ANTHEM)
    other = conn.execute(
        text("INSERT INTO ref.payer (canonical_name) VALUES ('Other Payer') RETURNING id")
    ).scalar_one()
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.payer_alias (raw_text, raw_normalized, payer_id, match_type) "
                "VALUES (:r, :k, :p, 'manual')"
            ),
            {"r": ANTHEM, "k": normalize_name(ANTHEM), "p": other},
        )


def test_mapped_alias_requires_payer_and_vice_versa(conn: Connection) -> None:
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.payer_alias (raw_text, raw_normalized, match_type) "
                "VALUES ('X', 'x', 'exact')"
            )
        )


def test_approval_requires_reviewer(conn: Connection) -> None:
    payer_id = conn.execute(
        text("INSERT INTO ref.payer (canonical_name) VALUES ('Y') RETURNING id")
    ).scalar_one()
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.payer_alias (raw_text, raw_normalized, payer_id, match_type, "
                "review_state) VALUES ('Y', 'y', :p, 'exact', 'approved')"
            ),
            {"p": payer_id},
        )
