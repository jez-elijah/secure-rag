"""Central settings: paths, model names, retrieval size, and role permissions."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Defaults are relative to the working directory; override with env vars when using the
# package from elsewhere (for example in a container or as an installed library).
DOCS_DIR = Path(os.getenv("SECURE_RAG_DOCS_DIR", "data/docs"))
DB_DIR = os.getenv("SECURE_RAG_DB_DIR", "chroma_db")
AUDIT_LOG = Path(os.getenv("SECURE_RAG_AUDIT_LOG", "logs/audit.jsonl"))

MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")  # set LLM_MODEL in .env to change
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
K = 5
CHUNK_MIN_CHARS = 400

# Which document departments each role may search. Enforced at retrieval time.
ROLE_ACCESS = {
    "employee": ["public"],
    "hr": ["public", "hr"],
    "finance": ["public", "finance"],
    "engineering": ["public", "engineering"],
    "admin": ["public", "hr", "finance", "engineering"],
}
