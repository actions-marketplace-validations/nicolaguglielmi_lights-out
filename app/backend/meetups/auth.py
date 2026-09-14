"""stdlib auth: scrypt password hashes, opaque bearer session tokens (docs/adr/0005)."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import Depends, Header, HTTPException

from meetups.db import get_db

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SESSION_LIFETIME = timedelta(days=7)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    candidate = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
    )
    return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))


def issue_session(cur: psycopg.Cursor, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
    cur.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (token_hash, user_id, expires_at),
    )
    return token


def current_user_id(
    authorization: str | None = Header(default=None),
    db: psycopg.Connection = Depends(get_db),
) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db.cursor() as cur:
        cur.execute(
            "SELECT user_id FROM sessions WHERE token_hash = %s AND expires_at > now()",
            (token_hash,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return row[0]
