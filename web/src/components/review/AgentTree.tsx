"use client";

import type { AgentNode, SourceInfo } from "@/lib/types";

const STATUS: Record<string, { dot: string; text: string }> = {
  ok: { dot: "bg-[var(--vt-ok)]", text: "done" },
  not_checked: { dot: "bg-[var(--vt-blocker)]", text: "not checked" },
  failed: { dot: "bg-[var(--vt-blocker)]", text: "failed" },
  skipped: { dot: "bg-[var(--vt-warning)]", text: "skipped" },
  running: { dot: "bg-muted", text: "running" },
};

/** How Prism checked this submission: every agent it spawned, nested by who spawned whom. */
export function AgentTree({ agents }: { agents: AgentNode[] }) {
  const children = new Map<string | null, AgentNode[]>();
  for (const a of agents) children.set(a.parent, [...(children.get(a.parent) ?? []), a]);
  const total = agents.length;
  const deepest = Math.max(0, ...agents.map((a) => a.depth));
  const gaps = agents.filter((a) => a.status !== "ok" && a.status !== "running");

  function branch(parent: string | null) {
    const kids = children.get(parent) ?? [];
    if (!kids.length) return null;
    return (
      <ul className={parent ? "ml-3 border-l border-line pl-3" : ""}>
        {kids.map((a) => {
          const st = STATUS[a.status] ?? STATUS.running;
          return (
            <li key={a.id} className="py-0.5">
              <div className="flex min-w-0 items-center gap-2 text-xs">
                <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${st.dot}`} />
                <span className="truncate font-medium" title={a.label}>{a.label}</span>
                <span className="shrink-0 rounded bg-bg px-1 text-[11px] uppercase text-muted">{a.role}</span>
                {a.findings > 0 && <span className="shrink-0 text-[11px] text-accent">{a.findings} found</span>}
                <span className="ml-auto shrink-0 tabular-nums text-[11px] text-muted">{a.ms >= 1000 ? `${(a.ms / 1000).toFixed(1)} s` : `${a.ms} ms`}</span>
              </div>
              {a.note && <p className="ml-4 text-[11px] text-muted">{st.text}: {a.note}</p>}
              {branch(a.id)}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted">
        {total} agents, {deepest + 1} levels deep.{" "}
        {gaps.length ? <span className="font-medium text-[var(--vt-blocker)]">{gaps.length} could not finish; their parts count as not checked.</span>
          : "Every agent finished."}
      </p>
      <div className="max-h-[28rem] overflow-auto rounded-lg border border-line bg-surface p-3">{branch(null)}</div>
    </div>
  );
}

const ROUTE: Record<string, string> = {
  typed: "Typed",
  "pdf-text-layer": "PDF text layer",
  docx: "Word document",
  "ocr:local": "Read by local OCR",
  "ocr:local+vision": "Local OCR, re-read by vision model",
  "ocr:vision": "Read by vision model",
  "ocr:frames": "OCR of video frames",
  "subtitle-track": "Subtitle track",
};

/** Every piece of text Prism found, and how it was obtained. */
export function Sources({ sources }: { sources: SourceInfo[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {sources.map((s) => (
        <li key={s.id} className="rounded-lg border border-line bg-surface p-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <code className="rounded bg-bg px-1.5 py-0.5">{s.id}</code>
            <span className="text-muted">{ROUTE[s.route] ?? (s.route.startsWith("asr") ? "Speech, transcribed locally" : s.route)}</span>
            <span className="ml-auto text-muted">{s.chars.toLocaleString()} chars · confidence {Math.round(s.confidence * 100)}%</span>
          </div>
          {s.id !== "body" && (
            <p className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-xs leading-5 text-ink/80">{s.text || "(no text)"}</p>
          )}
        </li>
      ))}
    </ul>
  );
}
