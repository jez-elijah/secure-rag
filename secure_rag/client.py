"""A small, stable entry point for using Secure RAG as a library.

    from secure_rag import SecureRAG

    rag = SecureRAG()                       # redaction is ON by default
    rag.index("path/to/docs")               # *.md files named <department>_<name>.md
    result = rag.ask("What is the restocking fee?", role="employee")
    print(result["answer"], result["sources"])

Access control is applied at retrieval time from `role`; PII is redacted before any text
is sent to the model. Pass redact=False only for experiments on non-sensitive data.
"""
from secure_rag import pipeline
from secure_rag.ingest.indexer import build_index
from secure_rag.settings import K, ROLE_ACCESS


class SecureRAG:
    def __init__(self, redact=True, k=K):
        self.redact = redact
        self.k = k

    @property
    def roles(self):
        """Role name -> departments that role may search."""
        return {role: list(depts) for role, depts in ROLE_ACCESS.items()}

    def index(self, docs_dir=None):
        """(Re)build the vector index from markdown files in docs_dir."""
        build_index(docs_dir)

    def ask(self, question, role, redact=None, k=None):
        """Answer a question as `role`. `role` is required so that no call is unfiltered by accident.

        Returns the same dict as pipeline.ask(): answer, sources, invalid_citations,
        retrieved_docs, outgoing, timings_ms.
        """
        return pipeline.ask(
            question,
            k=k or self.k,
            user_role=role,
            redact=self.redact if redact is None else redact,
        )
