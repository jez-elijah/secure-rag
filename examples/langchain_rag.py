"""The Secure RAG flow rebuilt with LangChain (LCEL), reusing this project's governance pieces.

LangChain supplies the orchestration (retriever interface, prompt template, chat model,
output parser); the security behaviour is the same as pipeline.py:

    question -> role-filtered retriever -> PII redaction -> prompt -> Claude -> restore
             -> citation validation

Install the extra and run from the project root:
    pip install -e ".[langchain]"
    python examples/langchain_rag.py "What is the restocking fee?" --role=employee
"""
import sys

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from secure_rag.generation.citations import validate_citations
from secure_rag.generation.prompts import SYSTEM, SYSTEM_REDACTED, build_user_content
from secure_rag.retrieval.search import retrieve
from secure_rag.security.audit import audit
from secure_rag.security.pii import Redactor
from secure_rag.settings import K, MODEL


class RoleFilteredRetriever(BaseRetriever):
    """LangChain retriever whose vector search is limited to the role's departments.

    The role is fixed when the retriever is built (from the authenticated session), so a
    question can never widen its own access.
    """

    role: str
    k: int = K

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        chunks, metas = retrieve(query, self.k, self.role)
        return [Document(page_content=c, metadata=m) for c, m in zip(chunks, metas)]


def build_chain(role, redact=True, k=K, llm=None):
    """Return a runnable: question (str) -> {"answer", "sources", "invalid_citations", ...}.

    Build one chain per authenticated user/role. `llm` can be any LangChain chat model
    (defaults to ChatAnthropic with the project's MODEL); tests pass a fake.
    """
    if llm is None:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(model=MODEL, max_tokens=500)

    retriever = RoleFilteredRetriever(role=role, k=k)
    prompt = ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "{user}")])

    def fetch(question):
        return {"question": question, "docs": retriever.invoke(question)}

    def protect(state):
        # One Redactor per request so the same value keeps the same placeholder everywhere.
        redactor = Redactor() if redact else None
        docs = state["docs"]
        q_text = redactor.redact(state["question"]) if redact else state["question"]
        c_texts = [redactor.redact(d.page_content) if redact else d.page_content for d in docs]
        metas = [d.metadata for d in docs]
        audit(role, q_text, metas, redact)
        return {
            **state,
            "redactor": redactor,
            "metas": metas,
            "system": SYSTEM_REDACTED if redact else SYSTEM,
            "user": build_user_content(q_text, c_texts, metas),
        }

    def finish(state):
        answer = state["raw"]
        if state["redactor"] is not None:
            answer = state["redactor"].restore(answer)
        metas = state["metas"]
        valid, invalid = validate_citations(answer, len(metas))
        return {
            "answer": answer,
            "sources": [
                {"n": n, "doc_id": metas[n - 1]["doc_id"], "title": metas[n - 1]["title"]}
                for n in valid
            ],
            "invalid_citations": invalid,
            "retrieved_docs": [m["doc_id"] for m in metas],
            "outgoing": state["user"],
        }

    return (
        RunnableLambda(fetch)
        | RunnableLambda(protect)
        | RunnablePassthrough.assign(raw=prompt | llm | StrOutputParser())
        | RunnableLambda(finish)
    )


def main(argv):
    role = next((a.split("=", 1)[1] for a in argv if a.startswith("--role=")), "employee")
    redact = "--no-redact" not in argv
    words = [a for a in argv if not a.startswith("--")]
    if not words:
        sys.exit('usage: python examples/langchain_rag.py "question" [--role=hr] [--no-redact]')
    result = build_chain(role, redact=redact).invoke(" ".join(words))
    print("\n" + result["answer"] + "\n\nSources:")
    for s in result["sources"]:
        print(f"  [{s['n']}] {s['doc_id']} ({s['title']})")
    if result["invalid_citations"]:
        print(f"  WARNING: answer cited nonexistent sources {result['invalid_citations']}")


if __name__ == "__main__":
    main(sys.argv[1:])
