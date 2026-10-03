"""API tests. The pipeline is replaced by a fake, so no model, index, or API key is needed."""
import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from secure_rag import api
from secure_rag.security import auth


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(auth, "AUTH_LOG", tmp_path / "auth.jsonl")
    monkeypatch.setenv("AUTH_SECRET", "x" * 40)
    auth.create_user("hana", "pw-123", "hr")


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_ask(question, k, user_role, redact):
        seen.append({"question": question, "k": k, "role": user_role, "redact": redact})
        return {
            "answer": "Answer [1]",
            "sources": [{"n": 1, "doc_id": "hr_leave_policy.md", "title": "Leave"}],
            "invalid_citations": [],
            "retrieved_docs": ["hr_leave_policy.md"],
            "outgoing": "SECRET PAYLOAD",
            "timings_ms": {"retrieve": 1.0, "redact": 1.0, "llm": 1.0, "post": 0.1, "total": 3.1},
        }

    monkeypatch.setattr(api, "ask", fake_ask)
    return seen


client = TestClient(api.app)


def token(username="hana", password="pw-123"):
    r = client.post("/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_health_needs_no_auth():
    assert client.get("/health").json()["status"] == "ok"


def test_login_rejects_bad_credentials():
    assert client.post("/login", json={"username": "hana", "password": "wrong"}).status_code == 401
    assert client.post("/login", json={"username": "nobody", "password": "x"}).status_code == 401


def test_ask_requires_a_valid_token(calls):
    assert client.post("/ask", json={"question": "hi"}).status_code == 401
    assert client.post("/ask", json={"question": "hi"}, headers=bearer("garbage")).status_code == 401
    assert calls == []  # the pipeline was never reached


def test_ask_uses_role_from_database_and_forces_redaction(calls):
    r = client.post("/ask", json={"question": "Leave policy?"}, headers=bearer(token()))
    assert r.status_code == 200
    assert calls[0]["role"] == "hr" and calls[0]["redact"] is True


def test_response_never_includes_outgoing_payload(calls):
    r = client.post("/ask", json={"question": "Leave policy?"}, headers=bearer(token()))
    assert "outgoing" not in r.json() and "SECRET PAYLOAD" not in r.text
    assert r.json()["sources"][0]["doc_id"] == "hr_leave_policy.md"


def test_demotion_takes_effect_on_an_existing_token(calls):
    tok = token()
    auth.create_user("hana", "pw-123", "employee")  # demoted after the token was issued
    client.post("/ask", json={"question": "q"}, headers=bearer(tok))
    assert calls[0]["role"] == "employee"


def test_client_cannot_disable_redaction(calls):
    client.post("/ask", json={"question": "q", "redact": False}, headers=bearer(token()))
    assert calls[0]["redact"] is True


@pytest.mark.parametrize("body", [{"question": ""}, {"question": "x" * 2001}, {"question": "q", "k": 0}, {"question": "q", "k": 11}])
def test_invalid_requests_are_rejected(calls, body):
    assert client.post("/ask", json=body, headers=bearer(token())).status_code == 422


def test_model_failure_becomes_502(monkeypatch):
    def boom(*_, **__):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))

    monkeypatch.setattr(api, "ask", boom)
    r = client.post("/ask", json={"question": "q"}, headers=bearer(token()))
    assert r.status_code == 502
