"""Sending waiting emails (Q26): any service, retries, link bodies cleared."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import Connection, text

from procedurescout_core import mailer
from procedurescout_core.portal_auth import request_sign_in
from tests.conftest import as_role


class FakeSender:
    def __init__(self, fail_for: str = "") -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail_for = fail_for

    def send(self, to: str, subject: str, body: str) -> None:
        if to == self.fail_for:
            raise RuntimeError("mailbox unavailable")
        self.sent.append((to, subject, body))


def test_sends_clears_link_and_retries(conn: Connection) -> None:
    conn.execute(text("DELETE FROM prov.outbox"))
    with as_role(conn, "ps_portal"):  # exactly what the live site can do
        request_sign_in(conn, "ok@synthetic.test", "https://example.test")
        request_sign_in(conn, "bad@synthetic.test", "https://example.test")
        fake = FakeSender(fail_for="bad@synthetic.test")
        out = mailer.send_pending(conn, fake)
        # 2026-11-12: a sent email must never go out again (it went out 8 times live)
        assert mailer.send_pending(conn, fake).sent == 0
    assert (out.sent, out.failed, out.waiting) == (1, 1, 1)
    assert "/providers/sign-in/verify#" in fake.sent[0][2]
    body = conn.execute(
        text("SELECT body FROM prov.outbox WHERE to_email = 'ok@synthetic.test'")
    ).scalar_one()
    assert body == "(sent)"  # the one-time link is not kept
    for _ in range(mailer.MAX_ATTEMPTS):
        mailer.send_pending(conn, fake)
    attempts = conn.execute(
        text("SELECT attempts FROM prov.outbox WHERE to_email = 'bad@synthetic.test'")
    ).scalar_one()
    assert attempts == mailer.MAX_ATTEMPTS  # stops trying
    assert mailer.send_pending(conn, fake).waiting == 0
    conn.execute(
        text(
            "UPDATE prov.outbox SET sent_at = now() - interval '31 days' WHERE sent_at IS NOT NULL"
        )
    )
    assert mailer.delete_old_sent(conn) == 1  # owner housekeeping


def test_sender_choice() -> None:
    assert mailer.sender_from("", "") is None
    assert mailer.sender_from("resend", "ProcedureScout <hi@example.test>") is None  # no key
    assert isinstance(
        mailer.sender_from("resend", "hi@example.test", resend_api_key="re_test"),
        mailer.ResendSender,
    )
    assert isinstance(
        mailer.sender_from(
            "smtp",
            "hi@example.test",
            smtp_host="smtp.example.test",
            smtp_username="u",
            smtp_password="p",
        ),
        mailer.SmtpSender,
    )


def test_resend_request_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_post(url: str, **kw: Any) -> httpx.Response:
        seen.update(url=url, **kw)
        return httpx.Response(200, json={"id": "x"})

    monkeypatch.setattr(mailer.httpx, "post", fake_post)
    mailer.ResendSender("re_test", "hi@example.test").send("a@b.test", "Hi", "Body")
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"]["Authorization"] == "Bearer re_test"
    assert seen["json"] == {
        "from": "hi@example.test",
        "to": ["a@b.test"],
        "subject": "Hi",
        "text": "Body",
    }
    # replies go to a real inbox when one is set
    sender = mailer.sender_from(
        "resend", "hi@example.test", "re_test", reply_to="help@example.test"
    )
    assert sender is not None
    sender.send("a@b.test", "Hi", "Body")
    assert seen["json"]["reply_to"] == "help@example.test"
    monkeypatch.setattr(mailer.httpx, "post", lambda url, **kw: httpx.Response(422))
    with pytest.raises(RuntimeError):
        mailer.ResendSender("re_test", "hi@example.test").send("a@b.test", "Hi", "Body")
