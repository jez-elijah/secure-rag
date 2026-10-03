import json
from types import SimpleNamespace

from secure_rag import pipeline as n
from secure_rag.security.pii import Redactor

TEXT = (
    "If the bank rejects it, a check is mailed to 4471 Elmwood Drive, Memphis, TN 38118. "
    "Background reference: SSN 423-71-9056, date of birth March 9, 1988."
)
SECRETS = ["Elmwood", "38118", "March 9", "1988", "423-71-9056"]


def test_address_and_dob_are_redacted():
    out = Redactor().redact(TEXT)
    for secret in SECRETS:
        assert secret not in out


def test_address_and_dob_are_never_restored():
    r = Redactor()
    restored = r.restore(r.redact(TEXT))
    for secret in SECRETS:
        assert secret not in restored
    assert "[REDACTED]" in restored


def test_ordinary_dates_and_numbers_are_untouched():
    text = (
        "Deployments are frozen from November 15 through January 5, "
        "and expenses over $25,000 need approval."
    )
    assert Redactor().redact(text) == text


def _capture_payload(monkeypatch, question, role):
    sent = {}

    def fake_create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text="I don't know. [1]")])

    monkeypatch.setattr(n, "llm", SimpleNamespace(messages=SimpleNamespace(create=fake_create)))
    n.ask(question, user_role=role, redact=True)
    return json.dumps(sent)


def test_outgoing_payload_has_no_address(monkeypatch):
    payload = _capture_payload(
        monkeypatch,
        "If the bank rejects Priya Raman's direct deposit, where is the check mailed?",
        "finance",
    )
    assert "Elmwood" not in payload and "38118" not in payload


def test_outgoing_payload_has_no_dob(monkeypatch):
    payload = _capture_payload(monkeypatch, "What is Tyrone Whitfield's date of birth?", "hr")
    assert "1988" not in payload and "March 9" not in payload
