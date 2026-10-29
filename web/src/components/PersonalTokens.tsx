"use client";

import { useCallback, useEffect, useState } from "react";
import { createToken, isOffline, listTokens, relativeTime, revokeToken } from "@/lib/review-client";
import type { CreatedToken, PersonalToken } from "@/lib/types";
import { CheckIcon } from "./Icons";
import { useToast } from "./Toaster";
import { shownError } from "@/lib/errors";

const EXPIRY = [7, 30, 90] as const;

const when = (iso: string) => new Date(iso).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
const live = (t: PersonalToken) => !t.revoked_at && new Date(t.expires_at).getTime() > Date.now();

/**
 * Personal tokens: what the person pastes into their own AI client so it can use Verytas as them, through
 * the /mcp endpoint. The secret is returned once by the API, so it is held only in this component's state
 * until it is dismissed, and never written to storage.
 */
export function PersonalTokens() {
  const toast = useToast();
  const [tokens, setTokens] = useState<PersonalToken[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [write, setWrite] = useState(false);
  const [days, setDays] = useState<number>(30);
  const [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState<CreatedToken | null>(null);
  const [copied, setCopied] = useState<"token" | "command" | null>(null);

  const load = useCallback(() => {
    listTokens().then((t) => { setTokens(t); setError(null); })
      .catch((e: unknown) => setError(isOffline(e) ? "Demo mode: no account is connected." : shownError(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    setBusy(true);
    try {
      setFresh(await createToken(name.trim(), write ? ["read", "write"] : ["read"], days));
      setName("");
      load();
    } catch (e) {
      toast({ kind: "error", title: "Couldn't create the token", detail: shownError(e) });
    } finally {
      setBusy(false);
    }
  }

  async function revoke(t: PersonalToken) {
    if (!window.confirm(`Revoke "${t.name}"? Any AI client using it stops working at once.`)) return;
    try {
      await revokeToken(t.id);
      if (fresh?.id === t.id) setFresh(null);
      toast({ kind: "success", title: "Token revoked" });
      load();
    } catch (e) {
      toast({ kind: "error", title: "Couldn't revoke", detail: shownError(e) });
    }
  }

  async function copy(text: string, what: "token" | "command") {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied((c) => (c === what ? null : c)), 2000);
    } catch {
      toast({ kind: "error", title: "Couldn't copy", detail: "Select the text and copy it by hand" });
    }
  }

  // Mounted only after the dialog is opened in the browser, so window is always there. The endpoint is on the
  // same address as the app (the reverse proxy sends /mcp to the API).
  const url = `${window.location.origin}/mcp`;
  const command = (secret: string) => `claude mcp add --transport http verytas ${url} --header "Authorization: Bearer ${secret}"`;
  const active = (tokens ?? []).filter(live);
  const past = (tokens ?? []).filter((t) => !live(t));

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-sm font-medium">Personal tokens</p>
        <p className="mt-0.5 text-xs leading-5 text-muted">
          A personal token lets Claude Desktop, Claude Code or another MCP client read your content and reviews as you,
          and submit text for review if you allow it. It sees only what you can see. It can never decide on a finding,
          approve or publish: you do that here.
        </p>
      </div>

      {fresh && (
        <div role="status" className="rounded-xl border border-accent/40 bg-accent/5 p-3">
          <p className="text-sm font-medium">Copy your token now</p>
          <p className="mt-0.5 text-xs text-muted">You won&apos;t see it again. If you lose it, revoke it and make a new one.</p>
          <div className="mt-2 flex items-center gap-2">
            <code className="min-w-0 flex-1 select-all break-all rounded-lg bg-sunken px-2.5 py-2 font-mono text-xs">{fresh.token}</code>
            <button type="button" className="vt-btn vt-btn-sm vt-btn-primary shrink-0" onClick={() => copy(fresh.token, "token")}>
              {copied === "token" ? <><CheckIcon size={14} /> Copied</> : "Copy"}
            </button>
          </div>
          <p className="mt-3 text-xs font-medium text-muted">Connect Claude Code</p>
          <div className="mt-1 flex items-start gap-2">
            <code className="min-w-0 flex-1 select-all break-all rounded-lg bg-sunken px-2.5 py-2 font-mono text-xs">{command(fresh.token)}</code>
            <button type="button" className="vt-btn vt-btn-sm vt-btn-quiet shrink-0" onClick={() => copy(command(fresh.token), "command")}>
              {copied === "command" ? <><CheckIcon size={14} /> Copied</> : "Copy"}
            </button>
          </div>
          <button type="button" className="vt-btn vt-btn-sm vt-btn-quiet mt-3" onClick={() => setFresh(null)}>I&apos;ve saved it</button>
        </div>
      )}

      <form className="flex flex-col gap-3 rounded-xl border border-line p-3"
        onSubmit={(e) => { e.preventDefault(); if (name.trim() && !busy) void create(); }}>
        <p className="text-sm font-medium">New token</p>
        <label className="flex flex-col gap-1 text-xs font-medium text-muted">
          Name
          <input className="vt-input" value={name} maxLength={60} placeholder="e.g. Laptop, Claude Desktop"
            onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs font-medium text-muted">
            Access
            <select className="vt-input" value={write ? "write" : "read"} onChange={(e) => setWrite(e.target.value === "write")}>
              <option value="read">Read only</option>
              <option value="write">Read and write</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-muted">
            Expires after
            <select className="vt-input" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {EXPIRY.map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
          </label>
        </div>
        <p className="text-xs leading-5 text-muted">
          {write ? "Write lets the client submit text for review and add comments, as you."
            : "Read lets the client list your content, read reviews and findings, and search."}
          {" "}You can have up to five active tokens.
        </p>
        <button type="submit" className="vt-btn vt-btn-primary self-end" disabled={busy || !name.trim() || Boolean(error)}>
          {busy ? "Creating…" : "Create token"}
        </button>
      </form>

      <div>
        <p className="text-sm font-medium">Your tokens</p>
        {error && <p className="mt-2 text-xs text-muted">{error}</p>}
        {!error && tokens === null && <p className="mt-2 text-xs text-muted">Loading…</p>}
        {!error && tokens && active.length === 0 && <p className="mt-2 text-xs text-muted">No active tokens.</p>}
        <ul className="mt-2 flex flex-col gap-2">
          {active.map((t) => (
            <li key={t.id} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{t.name}</p>
                <p className="mt-0.5 text-xs text-muted">
                  <span className="font-mono">vt_pat_{t.prefix}…</span> · {t.scopes.includes("write") ? "Read and write" : "Read only"}
                  {" · "}{t.last_used_at ? `used ${relativeTime(t.last_used_at)}` : "never used"} · expires {when(t.expires_at)}
                </p>
              </div>
              <button type="button" className="vt-btn vt-btn-xs vt-btn-quiet shrink-0" onClick={() => revoke(t)}>Revoke</button>
            </li>
          ))}
        </ul>
        {past.length > 0 && (
          <p className="mt-2 text-xs text-subtle">
            {past.length} revoked or expired token{past.length === 1 ? "" : "s"} no longer work.
          </p>
        )}
      </div>

      <div className="rounded-xl bg-sunken p-3">
        <p className="text-xs font-medium text-muted">Connect your AI client</p>
        <p className="mt-1 text-xs leading-5 text-muted">Claude Code:</p>
        <code className="mt-1 block select-all break-all font-mono text-xs">{command("<token>")}</code>
        <p className="mt-2 text-xs leading-5 text-muted">
          Other clients: add a remote MCP server at <span className="font-mono">{url}</span> with the header
          {" "}<span className="font-mono">Authorization: Bearer &lt;token&gt;</span>.
        </p>
      </div>
    </div>
  );
}
