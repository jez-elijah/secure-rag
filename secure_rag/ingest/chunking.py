"""Split documents into chunks."""
import re

from secure_rag.settings import CHUNK_MIN_CHARS


def chunk_text(text, min_chars=CHUNK_MIN_CHARS):
    """Split on blank lines, then merge paragraphs until a chunk is at least min_chars long."""
    chunks, buf = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        buf = f"{buf}\n\n{para}" if buf else para
        if len(buf) >= min_chars:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks
