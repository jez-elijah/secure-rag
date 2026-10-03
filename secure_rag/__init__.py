"""Secure RAG: role-filtered retrieval, PII redaction before the LLM call, validated citations."""
from secure_rag.client import SecureRAG
from secure_rag.generation.citations import validate_citations
from secure_rag.security.pii import Redactor
from secure_rag.settings import ROLE_ACCESS

__version__ = "0.1.0"
__all__ = ["SecureRAG", "Redactor", "validate_citations", "ROLE_ACCESS", "__version__"]
