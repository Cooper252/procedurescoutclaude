import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from procedurescout_core.enums import ImportState as S
from procedurescout_core.import_state import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    can_transition,
    transition,
)
from tests.conftest import make_facility, make_import_run

HAPPY_PATH = [
    S.DISCOVERED,
    S.QUEUED,
    S.DOWNLOADING,
    S.DOWNLOADED,
    S.VALIDATING,
    S.PARSING,
    S.NORMALIZING,
    S.LOADING,
    S.QUALITY_REVIEW,
    S.PUBLISHED,
]


def test_happy_path_allowed() -> None:
    state = HAPPY_PATH[0]
    for nxt in HAPPY_PATH[1:]:
        state = transition(state, nxt)
    assert state is S.PUBLISHED


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.PUBLISHED, S.PARSING),
        (S.DISCOVERED, S.PUBLISHED),
        (S.PARSING, S.PUBLISHED),  # cannot skip normalization, loading, review
        (S.RETIRED, S.PUBLISHED),
        (S.PUBLISHED, S.FAILED),  # a published dataset never "fails"; a new run does
    ],
)
def test_illegal_transitions_raise(current: S, target: S) -> None:
    assert not can_transition(current, target)
    with pytest.raises(IllegalTransitionError):
        transition(current, target)


def test_every_working_state_can_fail() -> None:
    for state in HAPPY_PATH[1:-1]:
        assert can_transition(state, S.FAILED), state


def test_db_transition_table_matches_python(conn: Connection) -> None:
    rows = conn.execute(text("SELECT from_state::text, to_state::text FROM src.import_transition"))
    in_db = {(S(a), S(b)) for a, b in rows}
    assert in_db == set(ALLOWED_TRANSITIONS)


def test_db_trigger_allows_legal_and_logs_events(conn: Connection) -> None:
    run_id = make_import_run(conn, make_facility(conn))
    for nxt in HAPPY_PATH[1:4]:
        conn.execute(
            text("UPDATE src.import_run SET state = :s WHERE id = :id"), {"s": nxt, "id": run_id}
        )
    events = conn.execute(
        text(
            "SELECT to_state::text FROM src.import_run_event WHERE import_run_id = :id ORDER BY id"
        ),
        {"id": run_id},
    ).scalars()
    assert list(events) == ["discovered", "queued", "downloading", "downloaded"]


def test_db_trigger_rejects_illegal_jump(conn: Connection) -> None:
    run_id = make_import_run(conn, make_facility(conn))
    with pytest.raises(IntegrityError, match="illegal import transition"):
        conn.execute(
            text("UPDATE src.import_run SET state = 'published' WHERE id = :id"), {"id": run_id}
        )


def test_db_rejects_run_not_starting_discovered(conn: Connection) -> None:
    run_id = make_import_run(conn, make_facility(conn))
    file_id = conn.execute(
        text("SELECT file_id FROM src.import_run WHERE id = :id"), {"id": run_id}
    ).scalar_one()
    with pytest.raises(IntegrityError, match="must start in state discovered"):
        conn.execute(
            text(
                "INSERT INTO src.import_run (file_id, parser_version, state) "
                "VALUES (:f, 'x', 'published')"
            ),
            {"f": file_id},
        )
