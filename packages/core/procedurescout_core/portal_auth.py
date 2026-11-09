"""Provider sign-in (PRV-01, D-050).

- Sign-in is a one-time link sent by email (valid 15 minutes, used once). An
  account is created the first time someone signs in; it can do nothing public
  until it is verified for a facility (membership) and has an authenticator app.
- A second step with an authenticator app (TOTP, RFC 6238) is required before
  any change can be made. Five wrong codes end the session.
- Only SHA-256 hashes of links and session tokens are stored.
- Emails go to prov.outbox; nothing sends them until an email service is chosen
  (Q26).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
import uuid
from dataclasses import dataclass
from urllib.parse import quote, urlparse

from sqlalchemy import Connection, text

LINK_MINUTES = 15
SESSION_DAYS = 14
MAX_LINKS_PER_HOUR = 5
MAX_MFA_FAILURES = 5
ISSUER = "ProcedureScout"
_EMAIL = re.compile(r"^[^@\s]{1,64}@[a-z0-9.-]{1,190}\.[a-z]{2,24}$")


class AuthError(ValueError):
    """Sign-in could not be completed (message is safe to show)."""


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    email: str
    display_name: str | None
    mfa_enabled: bool
    mfa_passed: bool


@dataclass(frozen=True, slots=True)
class Membership:
    facility_id: str
    facility_name: str
    role: str
    status: str


def new_token() -> tuple[str, bytes]:
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def normalize_email(email: str) -> str:
    e = email.strip().lower()
    if not _EMAIL.match(e):
        raise AuthError("Enter a valid email address.")
    return e


def request_sign_in(conn: Connection, email: str, site_url: str) -> str | None:
    """Queue a sign-in link. Returns the token (shown only in development), or
    None when the hourly limit is reached. The caller always answers the same
    way, so the page never reveals whether an account exists."""
    e = normalize_email(email)
    account_id = conn.execute(
        text(
            "INSERT INTO prov.account (email) VALUES (:e) "
            "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id"
        ),
        {"e": e},
    ).scalar_one()
    recent = conn.execute(
        text(
            "SELECT count(*) FROM prov.login_token WHERE account_id = :a "
            "AND created_at > now() - interval '1 hour'"
        ),
        {"a": account_id},
    ).scalar_one()
    if int(recent) >= MAX_LINKS_PER_HOUR:
        return None
    token, digest = new_token()
    conn.execute(
        text(
            "INSERT INTO prov.login_token (token_hash, account_id, expires_at) "
            "VALUES (:h, :a, now() + make_interval(mins => :m))"
        ),
        {"h": digest, "a": account_id, "m": LINK_MINUTES},
    )
    link = f"{site_url.rstrip('/')}/providers/sign-in/verify#{token}"
    conn.execute(
        text(
            "INSERT INTO prov.outbox (to_email, purpose, subject, body) "
            "VALUES (:e, 'sign_in', :s, :b)"
        ),
        {
            "e": e,
            "s": "Your ProcedureScout sign-in link",
            "b": (
                f"Use this link to sign in to ProcedureScout for providers:\n\n{link}\n\n"
                f"It works once and expires in {LINK_MINUTES} minutes. If you didn't ask "
                "for it, you can ignore this email."
            ),
        },
    )
    return token


def complete_sign_in(conn: Connection, token: str) -> tuple[str, Account]:
    """Exchange a sign-in link for a session token."""
    row = conn.execute(
        text(
            "UPDATE prov.login_token SET used_at = now() WHERE token_hash = :h "
            "AND used_at IS NULL AND expires_at > now() RETURNING account_id"
        ),
        {"h": token_hash(token)},
    ).first()
    if row is None:
        raise AuthError("This sign-in link has expired or was already used. Ask for a new one.")
    account_id = row[0]
    disabled = conn.execute(
        text("SELECT disabled_at FROM prov.account WHERE id = :a"), {"a": account_id}
    ).scalar()
    if disabled is not None:
        raise AuthError("This account is turned off. Contact us for help.")
    session, digest = new_token()
    conn.execute(
        text(
            "INSERT INTO prov.session (token_hash, account_id, expires_at) "
            "VALUES (:h, :a, now() + make_interval(days => :d))"
        ),
        {"h": digest, "a": account_id, "d": SESSION_DAYS},
    )
    conn.execute(
        text("UPDATE prov.account SET last_sign_in_at = now() WHERE id = :a"), {"a": account_id}
    )
    account = session_account(conn, session)
    assert account is not None
    return session, account


def session_account(conn: Connection, session: str | None) -> Account | None:
    if not session:
        return None
    row = conn.execute(
        text(
            """
            UPDATE prov.session s SET last_seen_at = now()
            FROM prov.account a
            WHERE s.token_hash = :h AND s.expires_at > now() AND a.id = s.account_id
              AND a.disabled_at IS NULL
            RETURNING a.id, a.email, a.display_name, a.totp_enabled_at IS NOT NULL,
                      s.mfa_passed_at IS NOT NULL
            """
        ),
        {"h": token_hash(session)},
    ).first()
    if row is None:
        return None
    return Account(str(row[0]), str(row[1]), row[2], bool(row[3]), bool(row[4]))


def sign_out(conn: Connection, session: str) -> None:
    conn.execute(text("DELETE FROM prov.session WHERE token_hash = :h"), {"h": token_hash(session)})


# ------------------------------------------------------------------ TOTP
def totp_code(secret_b32: str, at: int | None = None, step: int = 0) -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    counter = (int(time.time()) if at is None else at) // 30 + step
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def _totp_ok(secret_b32: str, code: str) -> bool:
    code = re.sub(r"\s", "", code)
    if not re.fullmatch(r"[0-9]{6}", code):
        return False
    return any(hmac.compare_digest(totp_code(secret_b32, step=s), code) for s in (-1, 0, 1))


def totp_setup(conn: Connection, account: Account) -> tuple[str, str]:
    """Start (or restart) authenticator setup. Returns the secret and the
    otpauth:// link the app reads from a QR code."""
    if account.mfa_enabled:
        raise AuthError("An authenticator app is already set up for this account.")
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    conn.execute(
        text("UPDATE prov.account SET totp_secret = :s WHERE id = :a"),
        {"s": secret, "a": account.id},
    )
    label = quote(f"{ISSUER}:{account.email}")
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={ISSUER}&digits=6&period=30"
    return secret, uri


def totp_verify(conn: Connection, session: str, code: str) -> None:
    """Check an authenticator code for this session (also finishes setup)."""
    row = conn.execute(
        text(
            "SELECT a.id, a.totp_secret, a.totp_enabled_at FROM prov.session s "
            "JOIN prov.account a ON a.id = s.account_id "
            "WHERE s.token_hash = :h AND s.expires_at > now()"
        ),
        {"h": token_hash(session)},
    ).first()
    if row is None:
        raise AuthError("Please sign in again.")
    account_id, secret, enabled = row
    if not secret:
        raise AuthError("Set up an authenticator app first.")
    if not _totp_ok(str(secret), code):
        failures = conn.execute(
            text(
                "UPDATE prov.session SET mfa_failures = mfa_failures + 1 "
                "WHERE token_hash = :h RETURNING mfa_failures"
            ),
            {"h": token_hash(session)},
        ).scalar_one()
        if int(failures) >= MAX_MFA_FAILURES:
            sign_out(conn, session)
            raise AuthError("Too many wrong codes. Please sign in again.")
        raise AuthError("That code didn't match. Check the time on your phone and try again.")
    if enabled is None:
        conn.execute(
            text("UPDATE prov.account SET totp_enabled_at = now() WHERE id = :a"),
            {"a": account_id},
        )
    conn.execute(
        text(
            "UPDATE prov.session SET mfa_passed_at = now(), mfa_failures = 0 WHERE token_hash = :h"
        ),
        {"h": token_hash(session)},
    )


# ------------------------------------------------------------- memberships
def memberships(conn: Connection, account_id: str) -> list[Membership]:
    rows = conn.execute(
        text(
            "SELECT m.facility_id, f.name, m.role, m.status FROM prov.membership m "
            "JOIN ref.facility f ON f.id = m.facility_id "
            "WHERE m.account_id = :a AND m.status IN ('pending', 'active') ORDER BY f.name"
        ),
        {"a": account_id},
    ).all()
    return [Membership(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows]


def _domain(host: str) -> str:
    host = host.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def claim(conn: Connection, account: Account, facility_id: str, note: str | None) -> Membership:
    """Ask to manage a facility's page. Verified at once when the account's
    email is on the facility's reviewed website domain; otherwise a person
    checks it (pending)."""
    try:
        fid = str(uuid.UUID(facility_id))
    except ValueError as exc:
        raise AuthError("Unknown facility.") from exc
    fac = conn.execute(
        text("SELECT name, website FROM ref.facility WHERE id = :f"), {"f": fid}
    ).first()
    if fac is None:
        raise AuthError("Unknown facility.")
    existing = conn.execute(
        text("SELECT role, status FROM prov.membership WHERE account_id = :a AND facility_id = :f"),
        {"a": account.id, "f": fid},
    ).first()
    if existing is not None and existing[1] in ("pending", "active"):
        return Membership(fid, str(fac[0]), str(existing[0]), str(existing[1]))
    has_owner = conn.execute(
        text(
            "SELECT 1 FROM prov.membership WHERE facility_id = :f AND role = 'owner' "
            "AND status = 'active'"
        ),
        {"f": fid},
    ).first()
    role = "editor" if has_owner else "owner"
    website = fac[1]
    email_domain = account.email.rsplit("@", 1)[1]
    matches = bool(website) and _domain(urlparse(str(website)).netloc) == email_domain
    status = "active" if matches else "pending"
    if note is not None and len(note) > 500:
        raise AuthError("Keep the note under 500 characters.")
    conn.execute(
        text(
            """
            INSERT INTO prov.membership (account_id, facility_id, role, status, note,
                verified_via, verified_by, verified_at)
            VALUES (:a, :f, :r, :s, :n, :via, :by, CASE WHEN :s = 'active' THEN now() END)
            ON CONFLICT (account_id, facility_id) DO UPDATE SET role = EXCLUDED.role,
                status = EXCLUDED.status, note = EXCLUDED.note,
                verified_via = EXCLUDED.verified_via, verified_by = EXCLUDED.verified_by,
                verified_at = EXCLUDED.verified_at
            """
        ),
        {
            "a": account.id,
            "f": fid,
            "r": role,
            "s": status,
            "n": note,
            "via": "email_domain" if matches else None,
            "by": "automatic (work email on the facility's reviewed website)" if matches else None,
        },
    )
    return Membership(fid, str(fac[0]), role, status)


def require_role(
    conn: Connection, account: Account | None, facility_id: str, roles: tuple[str, ...]
) -> None:
    """Raise unless the account is signed in with its authenticator and holds
    an active membership with one of these roles."""
    if account is None:
        raise PermissionError("Please sign in.")
    if not account.mfa_passed:
        raise PermissionError("Enter the code from your authenticator app first.")
    ok = conn.execute(
        text(
            "SELECT 1 FROM prov.membership WHERE account_id = :a "
            "AND facility_id = CAST(:f AS uuid) AND status = 'active' AND role = ANY(:r)"
        ),
        {"a": account.id, "f": facility_id, "r": list(roles)},
    ).first()
    if ok is None:
        raise PermissionError("You don't manage this page yet.")


def decide_membership(
    conn: Connection, account_id: str, facility_id: str, reviewer: str, approve: bool
) -> None:
    conn.execute(
        text(
            "UPDATE prov.membership SET status = :s, verified_via = CASE WHEN :s = 'active' "
            "THEN 'manual' END, verified_by = CASE WHEN :s = 'active' THEN :by END, "
            "verified_at = CASE WHEN :s = 'active' THEN now() END "
            "WHERE account_id = :a AND facility_id = :f AND status = 'pending'"
        ),
        {
            "s": "active" if approve else "rejected",
            "by": reviewer,
            "a": account_id,
            "f": facility_id,
        },
    )


# ------------------------------------------------------------------- staff
def add_staff(conn: Connection, email: str, role: str, granted_by: str) -> None:
    """Let a person use the review pages (ADM-02). They sign in like providers:
    email link plus authenticator app."""
    if role not in ("reviewer", "admin"):
        raise AuthError("Role must be reviewer or admin.")
    e = normalize_email(email)
    aid = conn.execute(
        text(
            "INSERT INTO prov.account (email) VALUES (:e) "
            "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id"
        ),
        {"e": e},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO prov.staff (account_id, role, added_by) VALUES (:a, :r, :b) "
            "ON CONFLICT (account_id) DO UPDATE SET role = EXCLUDED.role, "
            "added_by = EXCLUDED.added_by"
        ),
        {"a": aid, "r": role, "b": granted_by},
    )


def staff_role(conn: Connection, account: Account | None) -> str | None:
    """'reviewer' or 'admin' for a signed-in staff member who passed the
    authenticator step; otherwise None."""
    if account is None or not account.mfa_passed:
        return None
    role = conn.execute(
        text("SELECT role FROM prov.staff WHERE account_id = :a"), {"a": account.id}
    ).scalar()
    return None if role is None else str(role)
