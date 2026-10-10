// Thin client for the Secure RAG FastAPI service. All paths go through /api (see vite.config.js).

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, { token, body } = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the API running?");
  }
  if (!res.ok) {
    let detail = "Something went wrong.";
    try {
      const data = await res.json();
      // FastAPI returns a string for HTTPException and a list for validation errors.
      detail = typeof data.detail === "string" ? data.detail : "That request was not valid.";
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export const login = (username, password) => request("/login", { body: { username, password } });

// mode "rag" -> /ask (fixed pipeline), mode "agent" -> /agent (model chooses tool calls)
export const ask = (token, mode, question) =>
  request(mode === "agent" ? "/agent" : "/ask", { token, body: { question } });
