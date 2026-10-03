import json
from types import SimpleNamespace

from secure_rag import pipeline as n
from secure_rag.security.pii import Redactor

TEXT = (
    "Maria Santos requested leave. Her employee ID is EMP-20418, her SSN is 512-44-8291, "
    "her email is maria.santos@acmelogistics.com and her phone is (901) 555-0142."
)


def test_pii_removed_from_redacted_text():
    out = Redactor().redact(TEXT)
    for secret in ["Maria Santos", "EMP-20418", "512-44-8291",
                   "maria.santos@acmelogistics.com", "555-0142"]:
        assert secret not in out


def test_same_value_gets_same_placeholder():
    r = Redactor()
    a = r.redact("Maria Santos filed the request.")
    b = r.redact("Approved for Maria Santos.")
    assert "<PERSON_1>" in a and "<PERSON_1>" in b


def test_restore_returns_names_but_never_ssn():
    r = Redactor()
    out = r.redact(TEXT)
    restored = r.restore(out)
    assert "Maria Santos" in restored
    assert "512-44-8291" not in restored


def test_outgoing_api_payload_contains_no_pii(monkeypatch):
    sent = {}

    def fake_create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text="I don't know. [1]")])

    monkeypatch.setattr(n, "llm", SimpleNamespace(messages=SimpleNamespace(create=fake_create)))
    n.ask("What is Maria Santos's SSN?", user_role="hr", redact=True)

    payload = json.dumps(sent)
    assert "512-44-8291" not in payload
    assert "Maria Santos" not in payload


def test_possessive_does_not_create_a_second_placeholder():
    r = Redactor()
    a = r.redact("Who approved Priya Raman's reimbursement?")
    b = r.redact("Priya Raman submitted the request.")
    assert "<PERSON_1>'s reimbursement" in a
    assert "<PERSON_1>" in b
    assert "<PERSON_2>" not in a + b
    assert r.restore(a) == "Who approved Priya Raman's reimbursement?"
