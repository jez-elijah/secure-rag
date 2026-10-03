"""Build the vector index from data/docs/*.md.

Run from the project root:
    python -m secure_rag.ingest.indexer
"""
import sys
from pathlib import Path

from secure_rag.ingest.chunking import chunk_text
from secure_rag import resources
from secure_rag.settings import DOCS_DIR


def build_index(docs_dir=None):
    """Rebuild the vector index from docs_dir (default: settings.DOCS_DIR).
    Each chunk carries doc_id, title, and department metadata."""
    docs_dir = Path(docs_dir) if docs_dir else DOCS_DIR
    db, embedder = resources.db, resources.embedder
    try:
        db.delete_collection("docs")
    except Exception:
        pass
    collection = db.create_collection("docs")

    ids, texts, metas = [], [], []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        department = path.stem.split("_")[0]  # public / hr / finance / engineering
        for i, chunk in enumerate(chunk_text(text)):
            ids.append(f"{path.name}::{i}")
            texts.append(chunk)
            metas.append(
                {"doc_id": path.name, "title": title, "department": department, "chunk": i}
            )

    if not texts:
        sys.exit(f"No .md files found in {docs_dir}. Add your documents first.")

    embeddings = embedder.encode(texts, normalize_embeddings=True).tolist()
    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metas)
    print(f"Indexed {len(texts)} chunks from {len({m['doc_id'] for m in metas})} documents.")
    return collection


if __name__ == "__main__":
    build_index()
