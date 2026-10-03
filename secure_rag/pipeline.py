"""The RAG pipeline: retrieve (role-filtered) -> redact PII -> generate -> validate citations.

Command line (from the project root):
    python -m secure_rag.pipeline "your question" --role=hr --redact
    python -m secure_rag.pipeline --role=finance --redact        # interactive
    python -m secure_rag.pipeline --reindex                      # rebuild the index first
"""
import sys
from time import perf_counter

from secure_rag import resources
from secure_rag.generation.citations import validate_citations
from secure_rag.generation.prompts import SYSTEM, SYSTEM_REDACTED, build_user_content
from secure_rag.ingest.indexer import build_index
from secure_rag.retrieval.search import retrieve
from secure_rag.security.audit import audit
from secure_rag.security.pii import Redactor
from secure_rag.settings import K, MODEL

# Optional override of the LLM client (tests replace it with a fake). When None, the
# lazily created Anthropic client from resources is used.
llm = None


def _client():
    return llm if llm is not None else resources.llm


def _ms(start, end):
    return round((end - start) * 1000, 1)


def ask(question, k=K, user_role=None, redact=False):
    t0 = perf_counter()
    chunks, metas = retrieve(question, k, user_role)
    t1 = perf_counter()

    redactor = Redactor() if redact else None
    q_text = redactor.redact(question) if redact else question
    c_texts = [redactor.redact(c) for c in chunks] if redact else chunks
    audit(user_role, q_text, metas, redact)
    t2 = perf_counter()

    user_content = build_user_content(q_text, c_texts, metas)
    msg = _client().messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM_REDACTED if redact else SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    t3 = perf_counter()

    answer = msg.content[0].text
    if redact:
        answer = redactor.restore(answer)
    valid, invalid = validate_citations(answer, len(chunks))
    t4 = perf_counter()

    return {
        "answer": answer,
        "sources": [
            {"n": n, "doc_id": metas[n - 1]["doc_id"], "title": metas[n - 1]["title"]}
            for n in valid
        ],
        "invalid_citations": invalid,
        "retrieved_docs": [m["doc_id"] for m in metas],  # used for retrieval hit rate
        "outgoing": user_content,  # exactly what was sent to the LLM, used to test for leaks
        # Per-stage wall-clock time in milliseconds (the LLM stage is a network call).
        "timings_ms": {
            "retrieve": _ms(t0, t1),
            "redact": _ms(t1, t2),
            "llm": _ms(t2, t3),
            "post": _ms(t3, t4),
            "total": _ms(t0, t4),
        },
    }


def show(result):
    print("\n" + result["answer"])
    print("\nSources:")
    for s in result["sources"]:
        print(f"  [{s['n']}] {s['doc_id']} ({s['title']})")
    if not result["sources"]:
        print("  (none cited)")
    if result["invalid_citations"]:
        print(f"  WARNING: answer cited nonexistent sources {result['invalid_citations']}")


def main(argv):
    if "--reindex" in argv or resources.get_collection().count() == 0:
        build_index()
    role = next((a.split("=", 1)[1] for a in argv if a.startswith("--role=")), None)
    redact = "--redact" in argv
    words = [a for a in argv if not a.startswith("--")]
    if words:
        show(ask(" ".join(words), user_role=role, redact=redact))
        return
    while True:
        q = input("\nQuestion (blank to quit): ").strip()
        if not q:
            break
        show(ask(q, user_role=role, redact=redact))


def cli():
    """Console-script entry point (`secure-rag`)."""
    main(sys.argv[1:])


if __name__ == "__main__":
    cli()
