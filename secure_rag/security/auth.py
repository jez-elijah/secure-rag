"""Users, password hashing, and signed session tokens for the demo app.

Design points:
- Passwords are hashed with scrypt (stdlib) and a random per-user salt; never stored in plaintext.
- After login the app holds a signed JWT. On every request the role is looked up in the user
  database from the token's username, so the role can't be changed by editing the token, and
  deleting or demoting a user takes effect immediately.
- Login successes and failures are written to logs/auth.jsonl.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("SECURE_RAG_USERS_DB", "data/users.db"))
AUTH_LOG = Path(os.getenv("SECURE_RAG_AUTH_LOG", "logs/auth.jsonl"))
TOKEN_TTL_MINUTES = 30
VALID_ROLES = {"employee", "hr", "finance", "engineering", "admin"}
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def _secret():
    key = os.getenv("AUTH_SECRET", "")
    if len(key) < 32:
        raise RuntimeError(
            "Set AUTH_SECRET in .env (at least 32 characters). Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"'
        )
    return key


def _hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "username TEXT PRIMARY KEY, role TEXT NOT NULL, salt BLOB NOT NULL, pw_hash BLOB NOT NULL)"
    )
    return conn


def _log(event, username, role=None):
    AUTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user": username,
        "role": role,
    }
    with AUTH_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def create_user(username, password, role):
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {role}")
    salt = secrets.token_bytes(16)
    with closing(_conn()) as conn, conn:  # inner `with conn` commits the transaction
        conn.execute(
            "INSERT OR REPLACE INTO users (username, role, salt, pw_hash) VALUES (?, ?, ?, ?)",
            (username, role, salt, _hash(password, salt)),
        )


def authenticate(username, password):
    """Return {'username', 'role'} for valid credentials, else None."""
    with closing(_conn()) as conn:
        row = conn.execute(
            "SELECT role, salt, pw_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        _hash(password, b"\x00" * 16)  # spend similar time so unknown users aren't detectable
        _log("login_failed", username)
        return None
    role, salt, stored = row
    if hmac.compare_digest(_hash(password, salt), stored):
        _log("login_ok", username, role)
        return {"username": username, "role": role}
    _log("login_failed", username)
    return None


def issue_token(user):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_token(token):
    """Return {'username', 'role'} for a valid token, else None.

    The role comes from the database, not from the token's own claim.
    """
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])  # algorithm pinned on purpose
    except jwt.PyJWTError:
        return None
    with closing(_conn()) as conn:
        row = conn.execute("SELECT role FROM users WHERE username = ?", (claims["sub"],)).fetchone()
    if row is None:
        return None
    return {"username": claims["sub"], "role": row[0]}
