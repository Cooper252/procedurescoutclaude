"""Facility identity without false merges: aliases, health systems, relationships."""

import uuid

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from procedurescout_core.facility_repo import (
    FacilityMatchStatus,
    add_alias,
    approved_campus_parent,
    resolve_facility_by_name,
)
from procedurescout_ingest.reference.relationships import (
    load_reviewed_relationships,
    propose_relationship,
)
from tests.conftest import make_facility


def with_ccn(conn: Connection, ccn: str, name: str) -> uuid.UUID:
    fid = make_facility(conn, name)
    conn.execute(text("UPDATE ref.facility SET ccn = :c WHERE id = :f"), {"c": ccn, "f": fid})
    return fid


def test_name_resolves_only_exactly(conn: Connection) -> None:
    fid = make_facility(conn, "Synthetic Regional Medical Center")
    add_alias(
        conn,
        fid,
        "Synthetic Regional Medical Center",
        alias_type="cms_name",
        source="test",
        match_basis="ccn",
    )
    hit = resolve_facility_by_name(conn, "  SYNTHETIC REGIONAL medical center. ", "NV")
    assert (hit.status, hit.facility_id) == (FacilityMatchStatus.MATCHED, fid)
    assert resolve_facility_by_name(conn, "Synthetic Regional", "NV").status == "unmatched"
    assert resolve_facility_by_name(conn, "Synthetic Regional Medical Center", "CA").status == (
        "unmatched"
    )


def test_shared_name_is_ambiguous_not_merged(conn: Connection) -> None:
    a = make_facility(conn, "Synthetic Community Hospital A")
    b = make_facility(conn, "Synthetic Community Hospital B")
    for fid in (a, b):
        add_alias(
            conn,
            fid,
            "Synthetic Community Hospital",
            alias_type="mrf_name",
            source="test",
            match_basis="manual",
            reviewed_by="reviewer",
        )
    hit = resolve_facility_by_name(conn, "Synthetic Community Hospital", "NV")
    assert hit.status == FacilityMatchStatus.AMBIGUOUS
    assert hit.facility_id is None and set(hit.candidates) == {a, b}


def test_unreviewed_manual_alias_is_ignored(conn: Connection) -> None:
    fid = make_facility(conn, "Synthetic Hospital")
    add_alias(conn, fid, "Synth Hosp", alias_type="mrf_name", source="test", match_basis="manual")
    state = conn.execute(text("SELECT review_state::text FROM ref.facility_alias")).scalar()
    assert state == "proposed"
    assert resolve_facility_by_name(conn, "Synth Hosp", "NV").status == "unmatched"


def test_database_refuses_unreviewed_manual_approval(conn: Connection) -> None:
    fid = make_facility(conn)
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.facility_alias (facility_id, alias, alias_normalized, source, "
                "match_basis, review_state) VALUES (:f, 'X', 'x', 'test', 'manual', 'approved')"
            ),
            {"f": fid},
        )


def test_two_health_systems_may_share_a_name(conn: Connection) -> None:
    for sid in ("HSI1", "HSI2"):
        conn.execute(
            text(
                "INSERT INTO ref.health_system (name, source, source_system_id) "
                "VALUES ('Synthetic Health', 'ahrq_compendium', :s)"
            ),
            {"s": sid},
        )
    n = conn.execute(text("SELECT count(*) FROM ref.health_system")).scalar()
    assert n == 2


def test_health_system_link_needs_source(conn: Connection) -> None:
    fid = make_facility(conn)
    hs = conn.execute(
        text("INSERT INTO ref.health_system (name) VALUES ('Synthetic') RETURNING id")
    ).scalar()
    with pytest.raises(IntegrityError):
        conn.execute(
            text("UPDATE ref.facility SET health_system_id = :h WHERE id = :f"), {"h": hs, "f": fid}
        )


REVIEWED_HEADER = "parent_ccn,child_ccn,relationship_type,evidence,reviewed_by,reviewed_at\n"


def test_reviewed_relationships_load(conn: Connection) -> None:
    parent = with_ccn(conn, "SYN201", "Synthetic Main Campus")
    child = with_ccn(conn, "SYN202", "Synthetic North Campus")
    csv_text = REVIEWED_HEADER + (
        "SYN201,SYN202,campus_of,Synthetic evidence: hospital site lists both,tester,2026-11-04\n"
        "SYN201,SYN999,campus_of,x,tester,2026-11-04\n"
        "SYN201,SYN202,same_license,,tester,2026-11-04\n"
        "SYN202,SYN201,campus_of,reversed,tester,2026-11-04\n"
        "SYN201,SYN201,same_license,self,tester,2026-11-04\n"
    )
    stats = load_reviewed_relationships(conn, csv_text)
    assert stats.rows_loaded == 1
    assert [r.rule for r in stats.rejects] == [
        "facility_not_found",
        "unreviewed",
        "refused_by_database",
        "self_relationship",
    ]
    assert approved_campus_parent(conn, child) == parent


def test_proposed_relationship_is_not_used(conn: Connection) -> None:
    parent = make_facility(conn, "Synthetic A")
    child = make_facility(conn, "Synthetic B")
    propose_relationship(conn, parent, child, "campus_of", "test", "shared price file")
    assert approved_campus_parent(conn, child) is None


def test_child_has_one_approved_campus_parent(conn: Connection) -> None:
    p1, p2, child = (make_facility(conn, f"Synthetic {n}") for n in ("P1", "P2", "C"))
    sql = text(
        "INSERT INTO ref.facility_relationship (parent_facility_id, child_facility_id, "
        "relationship_type, source, evidence, review_state, reviewed_by, reviewed_at) "
        "VALUES (:p, :c, 'campus_of', 'test', 'e', 'approved', 'r', now())"
    )
    conn.execute(sql, {"p": p1, "c": child})
    with pytest.raises(IntegrityError):
        conn.execute(sql, {"p": p2, "c": child})


def test_relationship_approval_needs_evidence(conn: Connection) -> None:
    p, c = make_facility(conn, "Synthetic P"), make_facility(conn, "Synthetic C")
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.facility_relationship (parent_facility_id, child_facility_id, "
                "relationship_type, source, review_state, reviewed_by, reviewed_at) "
                "VALUES (:p, :c, 'campus_of', 'test', 'approved', 'r', now())"
            ),
            {"p": p, "c": c},
        )
