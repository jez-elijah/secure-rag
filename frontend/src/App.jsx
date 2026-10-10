import { useState } from "react";
import Login from "./Login.jsx";
import Chat from "./Chat.jsx";

// The token lives in memory only: a page refresh signs the user out. That is deliberate for a
// demo; a production app would use an httpOnly cookie issued by the server.
export default function App() {
  const [session, setSession] = useState(null); // { token, username }

  if (!session) return <Login onLogin={setSession} />;
  return <Chat session={session} onLogout={() => setSession(null)} />;
}
