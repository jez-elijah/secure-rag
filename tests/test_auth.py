import time

import jwt
import pytest

from secure_rag.security import auth


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Use a throwaway database and log so tests never touch the real users."""
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(auth, "AUTH_LOG", tmp_path / "auth.jsonl")
    monkeypatch.setenv("AUTH_SECRET", "x" * 40)


def test_correct_password_authenticates():
    auth.create_user("hana", "pw-123", "hr")
    assert auth.authenticate("hana", "pw-123") == {"username": "hana", "role": "hr"}


def test_wrong_password_and_unknown_user_are_rejected():
    auth.create_user("hana", "pw-123", "hr")
    assert auth.authenticate("hana", "wrong") is None
    assert auth.authenticate("nobody", "pw-123") is None


def test_password_is_not_stored_in_plaintext():
    auth.create_user("hana", "pw-123", "hr")
    assert b"pw-123" not in auth.DB_PATH.read_bytes()


def test_valid_token_round_trip():
    auth.create_user("hana", "pw-123", "hr")
    token = auth.issue_token(auth.authenticate("hana", "pw-123"))
    assert auth.verify_token(token) == {"username": "hana", "role": "hr"}


def test_forged_token_is_rejected():
    auth.create_user("hana", "pw-123", "hr")
    forged = jwt.encode(
        {"sub": "hana", "role": "admin", "exp": time.time() + 600},
        "some-other-secret-that-is-long-enough",
        algorithm="HS256",
    )
    assert auth.verify_token(forged) is None


def test_expired_token_is_rejected(monkeypatch):
    auth.create_user("hana", "pw-123", "hr")
    monkeypatch.setattr(auth, "TOKEN_TTL_MINUTES", -1)
    token = auth.issue_token({"username": "hana", "role": "hr"})
    assert auth.verify_token(token) is None


def test_role_comes_from_database_not_from_token():
    auth.create_user("hana", "pw-123", "hr")
    token = auth.issue_token({"username": "hana", "role": "admin"})  # token claims admin
    assert auth.verify_token(token)["role"] == "hr"


def test_token_for_unknown_user_is_rejected():
    token = auth.issue_token({"username": "ghost", "role": "admin"})
    assert auth.verify_token(token) is None


def test_auth_roles_match_pipeline_roles():
    from secure_rag.settings import ROLE_ACCESS

    assert auth.VALID_ROLES == set(ROLE_ACCESS)
