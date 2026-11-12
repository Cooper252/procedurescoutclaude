"""Sends the emails waiting in prov.outbox (sign-in links, review links).

Works with Resend (HTTP API) or any SMTP service (Amazon SES, Postmark,
Brevo and others), chosen by settings (Q26). With no service configured
nothing is sent and emails keep waiting.

Privacy: once an email is sent its body (which holds a one-time link) is
cleared; sent rows are deleted after 30 days. Failed sends are retried up to
5 times within an hour; links expire on their own anyway.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import httpx
from sqlalchemy import Connection, text

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


class Sender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


@dataclass(frozen=True)
class ResendSender:
    api_key: str
    from_address: str
    endpoint: str = "https://api.resend.com/emails"
    reply_to: str = ""  # a real inbox (e.g. at IONOS) that replies go to

    def send(self, to: str, subject: str, body: str) -> None:
        payload: dict[str, object] = {
            "from": self.from_address,
            "to": [to],
            "subject": subject,
            "text": body,
        }
        if self.reply_to:
            payload["reply_to"] = self.reply_to
        r = httpx.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=15,
        )
        if r.status_code >= 300:
            raise RuntimeError(f"email service answered {r.status_code}")


@dataclass(frozen=True)
class SmtpSender:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    reply_to: str = ""

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.from_address
        msg["To"] = to
        if self.reply_to:
            msg["Reply-To"] = self.reply_to
        msg["Subject"] = subject
        msg.set_content(body)
        context = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=15) as s:
                s.login(self.username, self.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=15) as s:
                s.starttls(context=context)
                s.login(self.username, self.password)
                s.send_message(msg)


def sender_from(
    provider: str,
    from_address: str,
    resend_api_key: str = "",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_username: str = "",
    smtp_password: str = "",
    reply_to: str = "",
) -> Sender | None:
    """The configured sender, or None when email is not set up yet."""
    if not from_address:
        return None
    if provider == "resend" and resend_api_key:
        return ResendSender(resend_api_key, from_address, reply_to=reply_to.strip())
    if provider == "smtp" and smtp_host and smtp_username and smtp_password:
        return SmtpSender(
            smtp_host, smtp_port, smtp_username, smtp_password, from_address, reply_to.strip()
        )
    return None


@dataclass(frozen=True, slots=True)
class SendResult:
    sent: int
    failed: int
    waiting: int


def send_pending(conn: Connection, sender: Sender, limit: int = 50) -> SendResult:
    """Send waiting emails (oldest first). Never raises for one bad email."""
    rows = conn.execute(
        text(
            """
            SELECT id, to_email, subject, body FROM prov.outbox
            WHERE sent_at IS NULL AND attempts < :max
              AND created_at > now() - interval '1 hour'
            ORDER BY created_at LIMIT :n FOR UPDATE SKIP LOCKED
            """
        ),
        {"max": MAX_ATTEMPTS, "n": limit},
    ).all()
    sent = failed = 0
    for oid, to, subject, body in rows:
        try:
            sender.send(str(to), str(subject), str(body))
        except Exception as exc:  # one bad address must not stop the rest
            failed += 1
            log.warning("email %s not sent: %s", oid, type(exc).__name__)
            conn.execute(
                text("UPDATE prov.outbox SET attempts = attempts + 1, error = :e WHERE id = :i"),
                {"e": f"{type(exc).__name__}: {str(exc)[:200]}", "i": oid},
            )
            continue
        sent += 1
        conn.execute(
            text(
                "UPDATE prov.outbox SET sent_at = now(), body = '(sent)', error = NULL, "
                "attempts = attempts + 1 WHERE id = :i"
            ),
            {"i": oid},
        )
    waiting = conn.execute(
        text("SELECT count(*) FROM prov.outbox WHERE sent_at IS NULL AND attempts < :max"),
        {"max": MAX_ATTEMPTS},
    ).scalar_one()
    return SendResult(sent, failed, int(waiting))


def delete_old_sent(conn: Connection) -> int:
    """Remove emails sent more than 30 days ago. Owner connection only: the
    live site's portal role can't delete, and doing this inside send_pending
    rolled back the "sent" marks, so every email was re-sent every 5 minutes
    for an hour (found live, 2026-11-12)."""
    return conn.execute(
        text("DELETE FROM prov.outbox WHERE sent_at < now() - interval '30 days'")
    ).rowcount
