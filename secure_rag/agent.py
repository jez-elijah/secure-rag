"""Tool-calling agent on top of the secure RAG pipeline.

Instead of one fixed retrieve -> generate pass, the model decides which tools to call and
how often (for example: look at which departments the caller can search, run two different
searches, then answer). Security does not depend on the model behaving:

- The caller's role is bound server-side. It is never a tool argument, so the model cannot
  ask for another role's documents. Retrieval is filtered by that role (retrieval/search.py).
- Every retrieved chunk and the question are redacted before they go into the conversation,
  and placeholders are restored only in the final answer, same as pipeline.ask().
- The loop is capped at MAX_STEPS, unknown tools return an error to the model instead of
  crashing, and citations in the final answer are validated against the chunks actually
  retrieved.
"""
import json
from time import perf_counter

from secure_rag import pipeline
from secure_rag.generation.citations import validate_citations
from secure_rag.retrieval.search import retrieve
from secure_rag.security.audit import audit
from secure_rag.security.pii import Redactor
from secure_rag.settings import K, MODEL, ROLE_ACCESS

MAX_STEPS = 5

SYSTEM = (
    "You answer questions about company documents using tools. "
    "Use search_documents to find sources; you may search more than once with different queries. "
    "Cite sources as [1], [2] after each claim, using the numbers the tool returned. "
    "If the sources do not contain the answer, say you don't know. "
    "Personal data has been replaced by placeholders such as <PERSON_1> or <US_SSN_1>. "
    "When you refer to such a value, write the placeholder exactly as given."
)

TOOLS = [
    {
        "name": "search_documents",
        "description": (
            "Search the company documents the current user is allowed to see. Returns numbered "
            "passages. Cite them by number in your final answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."},
                "k": {"type": "integer", "description": "How many passages (1-10).", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_accessible_departments",
        "description": "List the document departments the current user may search.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


class _State:
    def __init__(self, role, redactor):
        self.role = role
        self.redactor = redactor
        self.chunks = []  # text exactly as sent to the model (redacted when redaction is on)
        self.metas = []

    def add(self, text, meta):
        """Number a chunk, reusing the number if the same passage was already returned."""
        for i, (c, m) in enumerate(zip(self.chunks, self.metas), 1):
            if c == text and m["doc_id"] == meta["doc_id"]:
                return i
        self.chunks.append(text)
        self.metas.append(meta)
        return len(self.chunks)


def _search(state, args):
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    k = max(1, min(int(args.get("k", K)), 10))
    # The model saw placeholders, so restore them for the local vector search only.
    local_query = state.redactor.restore(query) if state.redactor else query
    chunks, metas = retrieve(local_query, k, state.role)  # role comes from the server, not args
    lines = []
    for chunk, meta in zip(chunks, metas):
        text = state.redactor.redact(chunk) if state.redactor else chunk
        n = state.add(text, meta)
        lines.append(f"[{n}] ({meta['title']})\n{text}")
    return "\n\n".join(lines) if lines else "No passages found."


def _departments(state, _args):
    return ", ".join(ROLE_ACCESS[state.role])


_HANDLERS = {"search_documents": _search, "list_accessible_departments": _departments}


def _block_to_dict(block):
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": "text", "text": block.text}


def run_agent(question, user_role, redact=True, max_steps=MAX_STEPS):
    """Answer `question` as `user_role`, letting the model call tools. Returns a dict shaped
    like pipeline.ask() plus `steps`, a trace of every tool call."""
    if user_role not in ROLE_ACCESS:
        raise ValueError(f"Unknown role: {user_role}")
    t0 = perf_counter()
    redactor = Redactor() if redact else None
    state = _State(user_role, redactor)
    q_text = redactor.redact(question) if redact else question
    messages = [{"role": "user", "content": q_text}]
    steps = []
    answer = None

    for _ in range(max_steps):
        msg = pipeline._client().messages.create(
            model=MODEL, max_tokens=700, system=SYSTEM, tools=TOOLS, messages=messages
        )
        messages.append({"role": "assistant", "content": [_block_to_dict(b) for b in msg.content]})
        if msg.stop_reason != "tool_use":
            answer = "".join(b.text for b in msg.content if b.type == "text")
            break
        results = []
        for block in (b for b in msg.content if b.type == "tool_use"):
            handler = _HANDLERS.get(block.name)
            try:
                if handler is None:
                    raise ValueError(f"Unknown tool: {block.name}")
                output, is_error = handler(state, block.input), False
            except Exception as e:  # report the failure to the model; keep the loop alive
                output, is_error = f"Error: {e}", True
            steps.append({"tool": block.name, "input": block.input, "error": is_error})
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}
            )
        messages.append({"role": "user", "content": results})

    if answer is None:
        answer = "I could not finish within the allowed number of tool calls. Please rephrase or narrow the question."
    elif redact:
        answer = redactor.restore(answer)

    valid, invalid = validate_citations(answer, len(state.chunks))
    audit(user_role, q_text, state.metas, redact)
    return {
        "answer": answer,
        "sources": [
            {"n": n, "doc_id": state.metas[n - 1]["doc_id"], "title": state.metas[n - 1]["title"]}
            for n in valid
        ],
        "invalid_citations": invalid,
        "retrieved_docs": [m["doc_id"] for m in state.metas],
        "steps": steps,
        "outgoing": json.dumps(messages),  # everything sent to the LLM, used to test for leaks
        "timings_ms": {"total": round((perf_counter() - t0) * 1000, 1)},
    }
