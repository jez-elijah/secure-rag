"""Tests for the LangChain example, using a fake chat model (no API key, index, or embedder)."""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("langchain_core")
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

PATH = Path(__file__).resolve().parent.parent / "examples" / "langchain_rag.py"
spec = importlib.util.spec_from_file_location("langchain_rag", PATH)
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)

CHUNK = "Maria Santos requested leave. Her SSN is 512-44-8291."
META = {"doc_id": "hr_leave_policy.md", "title": "Leave", "department": "hr"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from secure_rag.security import audit as audit_mod

    monkeypatch.setattr(audit_mod, "AUDIT_LOG", tmp_path / "audit.jsonl")
    retrieved = {}

    def fake_retrieve(question, k, role):
        retrieved.update(question=question, k=k, role=role)
        return [CHUNK], [META]

    monkeypatch.setattr(lc, "retrieve", fake_retrieve)
    return retrieved


def fake_llm(reply):
    sent = {}

    def run(prompt_value):
        sent["text"] = prompt_value.to_string()
        return AIMessage(content=reply)

    return RunnableLambda(run), sent


def test_role_is_passed_to_the_retriever(setup):
    llm, _ = fake_llm("Leave is approved. [1]")
    lc.build_chain("hr", redact=False, llm=llm).invoke("Who requested leave?")
    assert setup["role"] == "hr"


def test_citations_are_validated(setup):
    llm, _ = fake_llm("Leave is approved [1], see also [9].")
    out = lc.build_chain("hr", redact=False, llm=llm).invoke("q")
    assert [s["doc_id"] for s in out["sources"]] == ["hr_leave_policy.md"]
    assert out["invalid_citations"] == [9]


def test_pii_never_reaches_the_model_and_ssn_is_never_restored(setup):
    llm, sent = fake_llm("<PERSON_1> asked for leave [1]. SSN: <US_SSN_1>.")
    out = lc.build_chain("hr", redact=True, llm=llm).invoke("What is Maria Santos's SSN?")
    assert "Maria Santos" not in sent["text"] and "512-44-8291" not in sent["text"]
    assert "Maria Santos asked for leave" in out["answer"]  # names are restored for the user
    assert "512-44-8291" not in out["answer"]  # SSNs never are
