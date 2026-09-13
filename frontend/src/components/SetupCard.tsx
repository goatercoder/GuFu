import { useState } from "react";
import { ApiError, useSetup } from "../api/client";

export default function SetupCard() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const setup = useSetup();
  const preview = `GuFu/0.1 (${name.trim() || "Your Name"}; ${email.trim() || "you@example.com"})`;
  const err = setup.error as ApiError | null;
  return (
    <div className="max-w-xl mx-auto card mt-8" data-testid="setup-card">
      <h1 className="text-2xl font-bold mb-1">Welcome to GuFu</h1>
      <p className="text-2 text-sm mb-4">
        One quick thing before we fetch data: the SEC's EDGAR service requires every request to identify who is asking.
        Enter a name and email and GuFu will include them in its requests to sec.gov. This is saved on this computer
        (in <code>.env</code>) and is never sent anywhere else.
      </p>
      <form onSubmit={(e) => { e.preventDefault(); setup.mutate({ name, email }); }} className="space-y-3">
        <label className="block text-sm">
          <span className="text-2 text-xs">Your name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" autoFocus required minLength={2} maxLength={80} aria-label="Your name" />
        </label>
        <label className="block text-sm">
          <span className="text-2 text-xs">Your email</span>
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@example.com" required maxLength={120} aria-label="Your email" />
        </label>
        <div className="text-xs muted">Requests to the SEC will identify as: <code>{preview}</code></div>
        {err && <div className="text-sm down">{err.message}</div>}
        <button type="submit" className="btn btn-active text-base px-4 py-2" disabled={setup.isPending}>
          {setup.isPending ? "Saving…" : "Start GuFu"}
        </button>
      </form>
      <p className="text-xs muted mt-4">
        After this, GuFu builds its S&amp;P 500 cache in the background (10–20 minutes). You can open company pages right away.
      </p>
    </div>
  );
}
