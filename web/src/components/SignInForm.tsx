"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

export function SignInForm() {
  const asked = useSearchParams().get("next");
  // Only same-site paths, so the form can't be used to bounce people elsewhere.
  const next = asked && asked.startsWith("/") && !asked.startsWith("//") ? asked : "/";
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (!res.ok) {
        setError((await res.json().catch(() => null))?.error ?? "Sign-in failed.");
        return;
      }
      // A full navigation, so server pages render with the new session.
      window.location.assign(next);
    } catch {
      setError("Couldn't reach the console server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm font-medium">
        API token
        <input type="password" autoComplete="current-password" required value={token}
          onChange={(e) => setToken(e.target.value)}
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm font-normal focus:border-accent focus:outline-none" />
      </label>
      {error && <p role="alert" className="text-sm text-[var(--vt-blocker)]">{error}</p>}
      <button type="submit" disabled={busy || !token.trim()}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink shadow-sm transition hover:brightness-110 disabled:opacity-50">
        {busy ? "Checking…" : "Sign in"}
      </button>
    </form>
  );
}
