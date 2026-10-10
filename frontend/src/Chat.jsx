import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ask } from "./api.js";

function Message({ m }) {
  if (m.from === "user") return <div className="msg user">{m.text}</div>;
  if (m.error) return <div className="msg error" role="alert">{m.text}</div>;
  return (
    <div className="msg bot">
      {/* The model's text is untrusted. react-markdown does not render raw HTML by default. */}
      <div className="answer"><ReactMarkdown>{m.text}</ReactMarkdown></div>
      {m.steps?.length > 0 && (
        <details>
          <summary>{m.steps.length} tool call{m.steps.length > 1 ? "s" : ""}</summary>
          <ol>
            {m.steps.map((s, i) => (
              <li key={i}>
                <code>{s.tool}</code>
                {s.input?.query ? ` "${s.input.query}"` : ""}
                {s.error ? " (failed)" : ""}
              </li>
            ))}
          </ol>
        </details>
      )}
      {m.sources?.length > 0 && (
        <ul className="sources">
          {m.sources.map((s) => (
            <li key={s.n}>[{s.n}] {s.title} <span className="muted">({s.doc_id})</span></li>
          ))}
        </ul>
      )}
      {m.invalid?.length > 0 && (
        <p className="warn">Warning: the answer cited sources that were not retrieved: {m.invalid.join(", ")}.</p>
      )}
      {m.ms != null && <p className="muted small">{Math.round(m.ms)} ms</p>}
    </div>
  );
}

export default function Chat({ session, onLogout }) {
  const [mode, setMode] = useState("rag");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, busy]);

  async function submit(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setMessages((m) => [...m, { from: "user", text: q }]);
    setBusy(true);
    try {
      const r = await ask(session.token, mode, q);
      setMessages((m) => [
        ...m,
        {
          from: "bot",
          text: r.answer,
          sources: r.sources,
          invalid: r.invalid_citations,
          steps: r.steps,
          ms: r.timings_ms?.total,
        },
      ]);
    } catch (err) {
      if (err.status === 401) return onLogout(); // token expired or invalid
      setMessages((m) => [...m, { from: "bot", error: true, text: err.message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="card chat">
      <header>
        <div>
          <h1>Secure RAG Assistant</h1>
          <p className="muted small">Signed in as {session.username}</p>
        </div>
        <button className="link" onClick={onLogout}>Sign out</button>
      </header>

      <div className="modes" role="radiogroup" aria-label="Answer mode">
        <label>
          <input type="radio" name="mode" checked={mode === "rag"} onChange={() => setMode("rag")} /> Standard RAG
        </label>
        <label>
          <input type="radio" name="mode" checked={mode === "agent"} onChange={() => setMode("agent")} /> Agent (tool calling)
        </label>
      </div>

      <div className="log" aria-live="polite">
        {messages.length === 0 && <p className="muted">Ask a question about your documents.</p>}
        {messages.map((m, i) => <Message key={i} m={m} />)}
        {busy && <div className="msg bot muted">Thinking...</div>}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="composer">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question"
          maxLength={2000}
          aria-label="Question"
        />
        <button type="submit" disabled={busy || !question.trim()}>Send</button>
      </form>
    </main>
  );
}
