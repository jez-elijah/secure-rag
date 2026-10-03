"""Shared heavyweight objects: embedding model, vector store client, and LLM client.

They are created on first use, not at import time, so importing the package is cheap and
does not need an API key or a model download (useful for tests, the API's health check,
and anyone using this as a library). Access them as attributes of this module:

    from secure_rag import resources
    resources.embedder, resources.llm, resources.db
"""
from secure_rag.settings import DB_DIR, EMBEDDING_MODEL

_cache = {}


def _create(name):
    if name == "embedder":
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(EMBEDDING_MODEL)
    if name == "llm":
        import anthropic

        return anthropic.Anthropic()
    import chromadb

    return chromadb.PersistentClient(path=DB_DIR)


def __getattr__(name):  # PEP 562: lazy module attributes
    if name in ("embedder", "llm", "db"):
        if name not in _cache:
            _cache[name] = _create(name)
        return _cache[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_collection():
    return __getattr__("db").get_or_create_collection("docs")
