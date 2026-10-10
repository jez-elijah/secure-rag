"""Agent tests. The LLM is a scripted fake and retrieval is replaced, so no API key, index,
or embedding model is needed (Presidio is still real, to test redaction)."""
import json
from types import SimpleNamespace

import pytest

from secure_rag import agent, pipeline
from secure_rag.security import audit as audit_mod

CHUNK = "Maria Santos requested leave. Her SSN is 512-44-8291."
META = {"doc_id": "hr_leave_policy.md", "title": "Leave", "department": "hr"}


def tool_use(name, tool_input, id_="t1"):
    block = SimpleNamespace(type="tool_use", id=id_, name=name, input=tool_input)
    return SimpleNamespace(content=[block], stop_reason="tool_use")


def final(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = self  # so fake.messages.create(...) works

    def create(self, **kwargs):
        self.calls.append(json.loads(json.dumps(kwargs["messages"])))
        return self.replies.pop(0) if self.replies else self.replies_default

    replies_default = None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_mod, "AUDIT_LOG", tmp_path / "audit.jsonl")
    retrieved = []

    def fake_retrieve(query, k, role):
        retrieved.append({"query": query, "k": k, "role": role})
        return [CHUNK], [META]

    monkeypatch.setattr(agent, "retrieve", fake_retrieve)

    def use(llm):
        monkeypatch.setattr(pipeline, "llm", llm)
        return llm

    return SimpleNamespace(retrieved=retrieved, use=use)


def test_model_can_search_then_answer_with_validated_citation(env):
    llm = env.use(FakeLLM([tool_use("search_documents", {"query": "leave"}), final("Leave is approved [1].")]))
    out = agent.run_agent("Who requested leave?", "hr", redact=False)
    assert out["answer"] == "Leave is approved [1]."
    assert out["sources"] == [{"n": 1, "doc_id": "hr_leave_policy.md", "title": "Leave"}]
    assert out["steps"] == [{"tool": "search_documents", "input": {"query": "leave"}, "error": False}]
    assert len(llm.calls) == 2


def test_role_comes_from_the_server_not_from_tool_arguments(env):
    env.use(FakeLLM([tool_use("search_documents", {"query": "salaries", "role": "admin"}), final("I don't know.")]))
    agent.run_agent("What are salaries?", "employee", redact=False)
    assert env.retrieved[0]["role"] == "employee"


def test_pii_never_reaches_the_llm_and_names_are_restored(env):
    env.use(FakeLLM([tool_use("search_documents", {"query": "leave"}), final("<PERSON_1> requested leave [1].")]))
    out = agent.run_agent("Who requested leave?", "hr", redact=True)
    assert "512-44-8291" not in out["outgoing"] and "Maria Santos" not in out["outgoing"]
    assert "Maria Santos requested leave" in out["answer"]


def test_invalid_citations_are_reported(env):
    env.use(FakeLLM([tool_use("search_documents", {"query": "leave"}), final("It is so [3].")]))
    out = agent.run_agent("q", "hr", redact=False)
    assert out["invalid_citations"] == [3] and out["sources"] == []


def test_loop_is_capped(env):
    llm = env.use(FakeLLM([]))
    llm.replies_default = tool_use("search_documents", {"query": "again"})
    out = agent.run_agent("q", "hr", redact=False, max_steps=3)
    assert len(llm.calls) == 3 and len(out["steps"]) == 3
    assert "could not finish" in out["answer"]


def test_unknown_tool_is_reported_to_the_model_not_raised(env):
    llm = env.use(FakeLLM([tool_use("delete_everything", {}), final("I don't know.")]))
    out = agent.run_agent("q", "hr", redact=False)
    assert out["steps"][0]["error"] is True
    assert llm.calls[1][-1]["content"][0]["is_error"] is True


def test_department_tool_reflects_the_callers_role(env):
    llm = env.use(FakeLLM([tool_use("list_accessible_departments", {}), final("done")]))
    agent.run_agent("q", "finance", redact=False)
    assert llm.calls[1][-1]["content"][0]["content"] == "public, finance"


def test_unknown_role_is_rejected(env):
    with pytest.raises(ValueError):
        agent.run_agent("q", "intern", redact=False)
