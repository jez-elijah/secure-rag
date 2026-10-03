FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/opt/hf
WORKDIR /app

# CPU-only PyTorch keeps the image much smaller than the default CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml README.md ./
COPY secure_rag ./secure_rag
RUN pip install ".[api]" && python -m spacy download en_core_web_lg

# Bake the embedding model into the image so containers start without a download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY data/docs ./data/docs
COPY scripts ./scripts

# Mutable state (vector index, users DB, logs) lives in /app/state, mounted as a volume.
ENV SECURE_RAG_DB_DIR=/app/state/chroma_db \
    SECURE_RAG_USERS_DB=/app/state/users.db \
    SECURE_RAG_AUDIT_LOG=/app/state/logs/audit.jsonl \
    SECURE_RAG_AUTH_LOG=/app/state/logs/auth.jsonl
RUN useradd --create-home app && mkdir -p /app/state && chown -R app /app /opt/hf
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "secure_rag.api:app", "--host", "0.0.0.0", "--port", "8000"]
