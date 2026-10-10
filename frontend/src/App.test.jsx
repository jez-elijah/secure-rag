import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

const json = (status, body) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });

function mockFetch(handler) {
  const fn = vi.fn((url, init) => handler(url, JSON.parse(init.body), init.headers));
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function signIn() {
  await userEvent.type(screen.getByLabelText("Username"), "hana");
  await userEvent.type(screen.getByLabelText("Password"), "pw");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("Secure RAG front end", () => {
  it("shows an error for bad credentials and stays on the login page", async () => {
    mockFetch(() => json(401, { detail: "Invalid username or password." }));
    render(<App />);
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password.");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("logs in, asks in standard mode with the bearer token, and shows answer and sources", async () => {
    const fetchMock = mockFetch((url) =>
      url === "/api/login"
        ? json(200, { access_token: "tok123" })
        : json(200, {
            answer: "Leave is 20 days [1].",
            sources: [{ n: 1, doc_id: "hr_leave_policy.md", title: "Leave" }],
            invalid_citations: [],
            timings_ms: { total: 1100 },
          })
    );
    render(<App />);
    await signIn();
    await userEvent.type(await screen.findByLabelText("Question"), "How much leave?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Leave is 20 days [1].")).toBeInTheDocument();
    expect(screen.getByText(/hr_leave_policy.md/)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls.at(-1);
    expect(url).toBe("/api/ask");
    expect(init.headers.Authorization).toBe("Bearer tok123");
  });

  it("uses /agent in agent mode and lists the tool calls", async () => {
    const fetchMock = mockFetch((url) =>
      url === "/api/login"
        ? json(200, { access_token: "t" })
        : json(200, {
            answer: "Done [1].",
            sources: [],
            invalid_citations: [],
            steps: [{ tool: "search_documents", input: { query: "restocking fee" }, error: false }],
            timings_ms: { total: 2500 },
          })
    );
    render(<App />);
    await signIn();
    await userEvent.click(await screen.findByLabelText(/Agent/));
    await userEvent.type(screen.getByLabelText("Question"), "fee?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("1 tool call")).toBeInTheDocument();
    expect(fetchMock.mock.calls.at(-1)[0]).toBe("/api/agent");
  });

  it("returns to the login page when the token is rejected", async () => {
    mockFetch((url) => (url === "/api/login" ? json(200, { access_token: "t" }) : json(401, { detail: "expired" })));
    render(<App />);
    await signIn();
    await userEvent.type(await screen.findByLabelText("Question"), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument());
  });

  it("renders markdown in answers and does not render raw HTML", async () => {
    mockFetch((url) =>
      url === "/api/login"
        ? json(200, { access_token: "t" })
        : json(200, {
            answer: "## Leave\n**16 weeks** of leave [1].\n\n<img src=x onerror=alert(1)>",
            sources: [],
            invalid_citations: [],
            timings_ms: { total: 10 },
          })
    );
    const { container } = render(<App />);
    await signIn();
    await userEvent.type(await screen.findByLabelText("Question"), "leave?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("heading", { name: "Leave" })).toBeInTheDocument();
    expect(screen.getByText("16 weeks").tagName).toBe("STRONG");
    expect(container.querySelector("img")).toBeNull();
  });
});
