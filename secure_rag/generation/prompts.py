"""Prompts and prompt assembly."""

SYSTEM = (
    "Answer using only the numbered sources provided. "
    "Cite sources as [1], [2] after each claim. "
    "If the sources don't contain the answer, say you don't know."
)
SYSTEM_REDACTED = SYSTEM + (
    " Personal data in the sources and question has been replaced by placeholders such as "
    "<PERSON_1> or <US_SSN_1>. When you refer to such a value, write the placeholder exactly as given."
)


def build_user_content(question, chunks, metas):
    context = "\n\n".join(
        f"[{i}] ({m['title']})\n{c}" for i, (c, m) in enumerate(zip(chunks, metas), 1)
    )
    return f"Sources:\n{context}\n\nQuestion: {question}"
