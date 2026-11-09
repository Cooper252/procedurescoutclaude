"""Provider portal (D-050): sign-in, claiming, homepage, images, reviews, counts.

All names, emails and pages here are synthetic test data, rolled back after each test.
"""

from __future__ import annotations

import struct
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from procedurescout_core import portal_auth as auth
from procedurescout_core import provider_pages as pages
from procedurescout_core import provider_stats as stats
from procedurescout_core import reviews
from procedurescout_core.object_store import LocalStore

from .conftest import make_facility

SITE = "https://example.test"
SECRET = "synthetic-test-secret"


def _facility(conn: Connection, website: str | None = None, geo: bool = True) -> str:
    fid = make_facility(conn, "Synthetic Portal Clinic")
    if website:
        conn.execute(
            text(
                "UPDATE ref.facility SET website = :w, website_reviewed_by = 'test', "
                "website_reviewed_at = now() WHERE id = :f"
            ),
            {"w": website, "f": fid},
        )
    if geo:
        conn.execute(
            text(
                "UPDATE ref.facility SET geom = ST_SetSRID(ST_MakePoint(-115.15, 36.17), 4326)"
                "::geography, geocode_source = 'synthetic', geocode_precision = 'address' "
                "WHERE id = :f"
            ),
            {"f": fid},
        )
    return str(fid)


def _signed_in(conn: Connection, email: str) -> tuple[str, auth.Account]:
    token = auth.request_sign_in(conn, email, SITE)
    assert token is not None
    return auth.complete_sign_in(conn, token)


def _with_mfa(conn: Connection, email: str) -> tuple[str, auth.Account]:
    session, account = _signed_in(conn, email)
    secret, uri = auth.totp_setup(conn, account)
    assert uri.startswith("otpauth://totp/ProcedureScout")
    auth.totp_verify(conn, session, auth.totp_code(secret))
    account2 = auth.session_account(conn, session)
    assert account2 is not None and account2.mfa_passed and account2.mfa_enabled
    return session, account2


def test_sign_in_link_works_once_and_is_hashed(conn: Connection) -> None:
    token = auth.request_sign_in(conn, "Owner@Synthetic-Clinic.test ", SITE)
    assert token is not None
    stored = conn.execute(text("SELECT token_hash FROM prov.login_token")).scalars().all()
    assert auth.token_hash(token) in [bytes(s) for s in stored]
    assert token.encode() not in [bytes(s) for s in stored]
    body = conn.execute(
        text("SELECT body FROM prov.outbox WHERE to_email = 'owner@synthetic-clinic.test'")
    ).scalar_one()
    assert f"{SITE}/providers/sign-in/verify#{token}" in body
    session, account = auth.complete_sign_in(conn, token)
    assert account.email == "owner@synthetic-clinic.test" and not account.mfa_passed
    with pytest.raises(auth.AuthError):
        auth.complete_sign_in(conn, token)
    auth.sign_out(conn, session)
    assert auth.session_account(conn, session) is None


def test_sign_in_links_are_rate_limited(conn: Connection) -> None:
    for _ in range(auth.MAX_LINKS_PER_HOUR):
        assert auth.request_sign_in(conn, "busy@synthetic.test", SITE) is not None
    assert auth.request_sign_in(conn, "busy@synthetic.test", SITE) is None
    with pytest.raises(auth.AuthError):
        auth.request_sign_in(conn, "not-an-email", SITE)


def test_authenticator_codes_and_lockout(conn: Connection) -> None:
    session, account = _signed_in(conn, "mfa@synthetic.test")
    with pytest.raises(auth.AuthError):
        auth.totp_verify(conn, session, "123456")  # no app set up yet
    secret, _ = auth.totp_setup(conn, account)
    assert auth.totp_code(secret, at=59) == auth.totp_code(secret, at=31)
    for _ in range(auth.MAX_MFA_FAILURES - 1):
        with pytest.raises(auth.AuthError, match="didn't match"):
            auth.totp_verify(conn, session, "000000" if auth.totp_code(secret) != "000000" else "1")
    with pytest.raises(auth.AuthError, match="Too many"):
        auth.totp_verify(conn, session, "000000" if auth.totp_code(secret) != "000000" else "1")
    assert auth.session_account(conn, session) is None


def test_claim_auto_verifies_on_the_facility_domain(conn: Connection) -> None:
    fid = _facility(conn, website="https://www.synthetic-clinic.test")
    _, owner = _with_mfa(conn, "boss@synthetic-clinic.test")
    m = auth.claim(conn, owner, fid, None)
    assert (m.role, m.status) == ("owner", "active")
    auth.require_role(conn, owner, fid, ("owner",))
    _, other = _with_mfa(conn, "someone@freemail.test")
    m2 = auth.claim(conn, other, fid, "I am the office manager")
    assert (m2.role, m2.status) == ("editor", "pending")
    with pytest.raises(PermissionError):
        auth.require_role(conn, other, fid, ("owner", "editor"))
    auth.decide_membership(conn, other.id, fid, "Synthetic Reviewer", approve=True)
    auth.require_role(conn, other, fid, ("owner", "editor"))


def test_changes_need_the_authenticator(conn: Connection) -> None:
    fid = _facility(conn, website="https://synthetic-clinic.test")
    _, account = _signed_in(conn, "nomfa@synthetic-clinic.test")
    auth.claim(conn, account, fid, None)
    with pytest.raises(PermissionError, match="authenticator"):
        auth.require_role(conn, account, fid, ("owner",))


def test_profile_is_reviewed_before_it_shows(conn: Connection) -> None:
    fid = _facility(conn)
    _, account = _with_mfa(conn, "editor@synthetic.test")
    form = {
        "about": "A synthetic test clinic.",
        "website_url": "synthetic-clinic.test",
        "hours": {"mon": "08:00-17:00", "sun": "closed"},
        "languages": ["Spanish", "English"],
        "accessibility": ["wheelchair_access"],
    }
    draft = pages.save_draft(conn, fid, account.id, form, submit=False)
    assert draft.status == "draft" and draft.website_url == "https://synthetic-clinic.test"
    assert draft.languages == ("English", "Spanish")
    assert pages.public_page(conn, fid).profile is None
    sub = pages.save_draft(conn, fid, account.id, form, submit=True)
    assert sub.status == "pending_review"
    assert sub.id is not None
    with pytest.raises(pages.PageError):
        pages.review_profile(conn, sub.id, "Synthetic Reviewer", approve=False, note="")
    pages.review_profile(conn, sub.id, "Synthetic Reviewer", approve=True, note=None)
    page = pages.public_page(conn, fid)
    assert page.profile is not None and page.profile.about == "A synthetic test clinic."
    # a second approved version replaces the first; only one is ever published
    second = pages.save_draft(conn, fid, account.id, {**form, "about": "Updated."}, submit=True)
    assert second.id is not None
    pages.review_profile(conn, second.id, "Synthetic Reviewer", approve=True, note=None)
    published = conn.execute(
        text("SELECT count(*) FROM prov.profile WHERE facility_id = :f AND status = 'published'"),
        {"f": fid},
    ).scalar_one()
    assert published == 1
    assert pages.public_page(conn, fid).profile.about == "Updated."  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "form",
    [
        {"website_url": "javascript:alert(1)"},
        {"hours": {"mon": "9 to 5"}},
        {"languages": ["Klingon"]},
        {"about": "<script>x</script>"},
        {"phone": "call me maybe"},
        {"unknown": "x"},
    ],
)
def test_profile_form_validation(form: dict[str, object]) -> None:
    with pytest.raises(pages.PageError):
        pages.clean(form)


def _png(w: int = 3, h: int = 2) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", w, h) + b"\x08\x06"


def test_images_are_checked_stored_and_reviewed(conn: Connection, tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    fid = _facility(conn)
    _, account = _with_mfa(conn, "photos@synthetic.test")
    assert pages.image_info(_png())[:4] == ("image/png", "png", 3, 2)
    with pytest.raises(pages.PageError):
        pages.image_info(b"GIF89a....")
    with pytest.raises(pages.PageError):
        pages.image_info(b"\x89PNG" + b"0" * pages.MAX_IMAGE_BYTES)
    mid = pages.upload_media(conn, store, fid, account.id, "logo", _png(), "Synthetic logo")
    key = conn.execute(
        text("SELECT object_key FROM prov.media WHERE id = :m"), {"m": mid}
    ).scalar_one()
    assert store.get_media(key) == _png()
    assert pages.media_is_published(conn, key) is None
    pages.review_media(conn, mid, "Synthetic Reviewer", approve=True)
    assert pages.media_is_published(conn, key) == "image/png"
    mid2 = pages.upload_media(conn, store, fid, account.id, "logo", _png(5, 5), None)
    pages.review_media(conn, mid2, "Synthetic Reviewer", approve=True)
    assert pages.public_page(conn, fid).logo_key != key  # the new logo replaced the old one


def test_email_confirmed_review_flow(conn: Connection) -> None:
    fid = _facility(conn)
    token = reviews.start_email_review(conn, fid, "patient@synthetic.test", SITE, SECRET)
    assert token is not None
    subject = conn.execute(
        text("SELECT subject FROM prov.outbox WHERE purpose = 'review_confirm'")
    ).scalar_one()
    assert subject == "Did you visit Synthetic Portal Clinic?"
    assert reviews.token_facility(conn, token)[2] == "email"
    with pytest.raises(reviews.ReviewError):
        reviews.submit_review(
            conn, token, rating=5, body="x" * 30, display_name="A", visited=True, independent=False
        )
    rid = reviews.submit_review(
        conn,
        token,
        rating=4,
        body="Price matched the quote and the staff were kind.",
        display_name="Sam P.",
        price_matched=True,
        visited=True,
        independent=True,
    )
    assert reviews.summary(conn, fid).count == 0  # waits for a person
    reviews.moderate(conn, rid, "Synthetic Moderator", publish=True)
    s = reviews.summary(conn, fid)
    assert (s.count, s.average, s.price_matched_yes) == (1, Decimal("4.0"), 1)
    assert reviews.published(conn, fid)[0].verification == "email"
    # the same email can't review the same provider again
    assert reviews.start_email_review(conn, fid, "patient@synthetic.test", SITE, SECRET) is None


def test_provider_invites_replies_and_reports(conn: Connection) -> None:
    fid = _facility(conn, website="https://synthetic-clinic.test")
    _, owner = _with_mfa(conn, "owner@synthetic-clinic.test")
    auth.claim(conn, owner, fid, None)
    invite = reviews.create_invite(conn, fid, owner.id)
    rid = reviews.submit_review(
        conn,
        invite,
        rating=1,
        body="Waited two hours and the bill was higher than quoted.",
        display_name="J.",
        price_matched=False,
        visited=True,
        independent=True,
    )
    with pytest.raises(reviews.ReviewError):  # each invite link works once
        reviews.token_facility(conn, invite)
    reviews.moderate(conn, rid, "Synthetic Moderator", publish=True)
    assert reviews.published(conn, fid)[0].verification == "provider_invite"
    assert reviews.reply(conn, rid, fid, owner.id, "We saw you on Oct 3 for your procedure.")
    assert not reviews.reply(conn, rid, fid, owner.id, "Thank you. Please call our billing team.")
    assert reviews.published(conn, fid)[0].reply_body is None  # reply waits for review
    reviews.review_reply(conn, rid, "Synthetic Moderator", approve=True)
    assert reviews.published(conn, fid)[0].reply_body is not None
    reviews.report(conn, rid, fid, owner.id, "Not a real patient")
    report_id = conn.execute(text("SELECT id FROM prov.review_report")).scalar_one()
    reviews.resolve_report(
        conn, str(report_id), "Synthetic Moderator", remove_reason="not_a_patient"
    )
    s = reviews.summary(conn, fid)
    assert (s.count, s.removed) == (0, 1)  # removed reviews are counted publicly


def test_providers_cannot_delete_reviews(engine: Engine, migrated: str) -> None:
    """The portal role can insert and update but has no DELETE on reviews."""
    with engine.connect() as c:
        has_role = c.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'ps_portal'")).first()
        if not has_role:
            pytest.skip("ps_portal role not created in this database")
        grants = {
            str(r[0])
            for r in c.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'ps_portal' AND table_schema = 'prov' "
                    "AND table_name = 'review'"
                )
            ).all()
        }
    assert {"SELECT", "INSERT", "UPDATE"} <= grants and "DELETE" not in grants


def test_public_api_role_reads_only_published_views(api_engine: Engine) -> None:
    with api_engine.connect() as c:
        c.execute(text("SELECT count(*) FROM prov.published_review")).scalar_one()
        c.execute(text("SELECT count(*) FROM prov.published_profile")).scalar_one()
        for table in ("prov.review", "prov.account", "prov.outbox", "stats.facility_daily"):
            with pytest.raises(DBAPIError):
                c.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
            c.rollback()


def test_counts_hide_small_numbers_and_estimate_boosts(conn: Connection) -> None:
    fid = _facility(conn)
    far = _facility(conn)
    conn.execute(
        text(
            "UPDATE ref.facility SET geom = "
            "ST_SetSRID(ST_MakePoint(-119.8, 39.5), 4326)::geography WHERE id = :f"
        ),
        {"f": far},
    )
    for _ in range(3):
        stats.record_event(conn, fid, "page_view")
    for _ in range(40):
        stats.record_search(conn, "svc:x-ray", Decimal("36.17"), Decimal("-115.15"), [far, fid])
    for _ in range(12):
        stats.record_search(conn, "svc:mri", Decimal("36.20"), Decimal("-115.10"), [far])
    stats.record_event(conn, fid, "website_click")
    d = stats.dashboard(conn, fid, 30)
    assert d.counts["page_view"].value is None  # 3 views → "fewer than 10"
    assert d.counts["page_view"].label == "fewer than 10"
    assert d.counts["search_impression"].value == 40
    assert d.average_position == Decimal("2.0")
    xray = next(s for s in d.services if s.service_key == "svc:x-ray")
    assert xray.offered and xray.shown == 40 and xray.searches[0] == 40
    assert [m.service_key for m in d.missed] == ["svc:mri"]
    boost = next(b for b in d.boosts if b.service_key == "svc:x-ray" and b.ring_miles == 10)
    assert (boost.searches, boost.estimated_views) == (40, 20)
    stored = conn.execute(text("SELECT DISTINCT place_key FROM stats.search_daily")).scalars().all()
    assert set(stored) == {"grid:36.1,-115.2", "grid:36.2,-115.1"}
    with pytest.raises(ValueError):
        stats.record_event(conn, fid, "search_impression")
    assert stats.service_key(None, "hcpcs", "70450") == "code:HCPCS:70450"
    assert stats.service_key("bad slug!", None, None) is None


def test_unknown_facility_ids_are_refused(conn: Connection) -> None:
    _, account = _with_mfa(conn, "x@synthetic.test")
    with pytest.raises(auth.AuthError):
        auth.claim(conn, account, str(uuid.uuid4()), None)
    with pytest.raises(reviews.ReviewError):
        reviews.start_email_review(conn, "not-a-uuid", "a@synthetic.test", SITE, SECRET)
