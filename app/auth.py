"""Demo auth: 2 seeded users, cookie session signed with stdlib hmac/hashlib
only (itsdangerous is deliberately not installed). Not real security -- a
fixed module-level secret is fine for a local demo app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User

SECRET = b"lean-mvp-demo-secret-not-for-prod"
COOKIE_NAME = "session"

SEED_USERS = [
    {"id": "sched1", "name": "Jordan (Front Desk)", "role": "scheduler"},
    {"id": "clin1", "name": "Dr. Patel (Clinical)", "role": "clinical"},
]

ALLOWED_TASK_TYPES = {
    "scheduler": {"scheduling"},
    "clinical": {"scheduling", "referral"},
}


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(s: str) -> bytes:
    padded = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(padded)


def sign_session(user_id: str) -> str:
    payload = json.dumps({"user_id": user_id}).encode()
    sig = hmac.new(SECRET, payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(sig)}"


def verify_session(cookie_value: str) -> str | None:
    try:
        payload_b64, sig_b64 = cookie_value.split(".", 1)
        payload = _b64decode(payload_b64)
        sig = _b64decode(sig_b64)
        expected_sig = hmac.new(SECRET, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return json.loads(payload)["user_id"]
    except Exception:
        return None


def get_current_user(
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_session),
) -> User:
    user_id = verify_session(session_cookie) if session_cookie else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="not logged in")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="not logged in")
    return user
