// Small pieces shared by the library tabs.

import type { ReactNode } from "react";

export function Field({ label, hint, children, className = "" }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`flex flex-col gap-1.5 text-xs font-medium ${className}`}>
      <span>{label}{hint && <span className="ml-1.5 font-normal text-subtle">{hint}</span>}</span>
      {children}
    </label>
  );
}

export function Badge({ tone = "muted", children }: { tone?: "muted" | "ok" | "warning" | "blocker" | "accent"; children: ReactNode }) {
  const cls = {
    muted: "bg-sunken text-muted",
    ok: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]",
    warning: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]",
    blocker: "bg-[var(--vt-blocker-bg)] text-[var(--vt-blocker)]",
    accent: "bg-accent/12 text-accent",
  }[tone];
  return <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-xl bg-sunken px-4 py-6 text-center text-sm text-muted">{children}</p>;
}

export function ReadOnlyNote() {
  return (
    <p className="mb-4 rounded-xl bg-sunken px-4 py-2.5 text-xs text-muted">
      You can read the library. Only brand admins change it.
    </p>
  );
}

export function ListSkeleton() {
  return <div className="flex flex-col gap-2">{[0, 1, 2, 3].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-sunken" />)}</div>;
}

/** Comma or newline separated text to a clean list, and back. */
export const toList = (s: string) => s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);
export const fromList = (xs: unknown) => (Array.isArray(xs) ? xs.join(", ") : "");

export const today = () => new Date().toISOString().slice(0, 10);
