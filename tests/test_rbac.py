import pytest

from secure_rag.retrieval.search import retrieve
from secure_rag.settings import ROLE_ACCESS

QUESTIONS = [
    "What is the Q3 fuel budget?",
    "How many weeks of parental leave?",
    "How fast must a SEV1 be acknowledged?",
    "Maria Santos SSN",
    "Who is on a performance improvement plan?",
]


@pytest.mark.parametrize("role", list(ROLE_ACCESS))
def test_only_allowed_departments_retrieved(role):
    allowed = set(ROLE_ACCESS[role])
    for q in QUESTIONS:
        _, metas = retrieve(q, k=10, user_role=role)
        assert {m["department"] for m in metas} <= allowed


def test_unknown_role_is_rejected():
    with pytest.raises(ValueError):
        retrieve("anything", user_role="intern")
