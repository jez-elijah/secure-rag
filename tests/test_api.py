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


# --- startup warm-up and server-side error logging ---------------------------------------

class _Coll:
    def __init__(self, n):
        self.n = n

    def count(self):
        return self.n


def test_startup_warms_models_after_index_check(monkeypatch):
    order = []
    monkeypatch.setattr(api.resources, "get_collection", lambda: _Coll(0))
    monkeypatch.setattr(api, "build_index", lambda: order.append("index"))
    monkeypatch.setattr(api, "warm_up", lambda: order.append("warm"))
    monkeypatch.setattr(api, "WARMUP", True)
    with TestClient(api.app) as c:
        assert c.get("/health").status_code == 200
    assert order == ["index", "warm"]


def test_warmup_can_be_disabled(monkeypatch):
    called = []
    monkeypatch.setattr(api.resources, "get_collection", lambda: _Coll(5))
    monkeypatch.setattr(api, "warm_up", lambda: called.append(1))
    monkeypatch.setattr(api, "WARMUP", False)
    with TestClient(api.app):
        pass
    assert called == []


def test_startup_fails_fast_without_auth_secret(monkeypatch):
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        with TestClient(api.app):
            pass


def test_model_error_is_logged_with_cause_but_not_leaked_to_client(monkeypatch, caplog):
    def boom(*_, **__):
        raise anthropic.BadRequestError(
            "credit balance is too low",
            response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
            body=None,
        )

    monkeypatch.setattr(api, "ask", boom)
    with caplog.at_level("ERROR", logger="uvicorn.error"):
        r = client.post("/ask", json={"question": "my secret question"}, headers=bearer(token()))
    assert r.status_code == 502
    assert "credit balance" not in r.text  # clients get a generic message
    assert "credit balance is too low" in caplog.text and "status=400" in caplog.text
    assert "my secret question" not in caplog.text  # the question is never logged
