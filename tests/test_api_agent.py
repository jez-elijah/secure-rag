"""/agent endpoint tests. The agent is replaced by a fake; no model, index, or API key needed."""
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

    def fake_agent(question, user_role, redact):
        seen.append({"question": question, "role": user_role, "redact": redact})
        return {
            "answer": "Answer [1]",
            "sources": [{"n": 1, "doc_id": "hr_leave_policy.md", "title": "Leave"}],
            "invalid_citations": [],
            "retrieved_docs": ["hr_leave_policy.md"],
            "steps": [{"tool": "search_documents", "input": {"query": "leave"}, "error": False}],
            "outgoing": "SECRET PAYLOAD",
            "timings_ms": {"total": 3.0},
        }

    monkeypatch.setattr(api, "run_agent", fake_agent)
    return seen


client = TestClient(api.app)


def token():
    return client.post("/login", json={"username": "hana", "password": "pw-123"}).json()["access_token"]


def test_agent_requires_a_valid_token(calls):
    assert client.post("/agent", json={"question": "hi"}).status_code == 401
    assert calls == []


def test_agent_uses_server_side_role_and_forces_redaction(calls):
    r = client.post("/agent", json={"question": "Leave?", "role": "admin", "redact": False},
                    headers={"Authorization": f"Bearer {token()}"})
    assert r.status_code == 200
    assert calls[0]["role"] == "hr" and calls[0]["redact"] is True
    assert r.json()["steps"][0]["tool"] == "search_documents"
    assert "SECRET PAYLOAD" not in r.text
