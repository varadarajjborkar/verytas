"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";

// Small notices that slide up from the bottom of the window: uploads finished,
// reviews done, anything that failed. They leave on their own (errors linger
// a little longer, and a hovered notice waits), or at once with the close button.

type Kind = "success" | "error" | "info" | "warning";
type Toast = { id: number; kind: Kind; title: string; detail?: string; duration: number; leaving?: boolean };
type ToastInput = { kind?: Kind; title: string; detail?: string; duration?: number };

const DURATION: Record<Kind, number> = { success: 4000, info: 5000, warning: 7000, error: 8000 };
const MAX_VISIBLE = 4;
const LEAVE_MS = 220;

const ToastContext = createContext<(t: ToastInput) => void>(() => {});

/** Auto-dismiss timers that pause while a notice is hovered or focused. */
class Timers {
  private items = new Map<number, { remaining: number; started: number; handle: ReturnType<typeof setTimeout> }>();

  constructor(private onDone: (id: number) => void) {}

  start(id: number, ms: number) {
    this.items.set(id, { remaining: ms, started: Date.now(), handle: setTimeout(() => this.onDone(id), ms) });
  }

  pause(id: number) {
    const t = this.items.get(id);
    if (!t) return;
    clearTimeout(t.handle);
    t.remaining -= Date.now() - t.started;
  }

  resume(id: number) {
    const t = this.items.get(id);
    if (!t) return;
    t.started = Date.now();
    t.handle = setTimeout(() => this.onDone(id), Math.max(1200, t.remaining));
  }

  clear() {
    this.items.forEach((t) => clearTimeout(t.handle));
  }
}

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    setTimeout(() => setToasts((all) => all.filter((t) => t.id !== id)), LEAVE_MS);
  }, []);

  const push = useCallback((input: ToastInput) => {
    const id = next.current++;
    const kind = input.kind ?? "info";
    const duration = input.duration ?? DURATION[kind];
    setToasts((all) => [...all.slice(-(MAX_VISIBLE - 1)), { id, kind, title: input.title, detail: input.detail, duration }]);
    return { id, duration };
  }, []);

  const timers = useRef<Timers | null>(null);
  const clock = () => (timers.current ??= new Timers(dismiss));

  const api = useCallback((input: ToastInput) => {
    const { id, duration } = push(input);
    (timers.current ??= new Timers(dismiss)).start(id, duration);
  }, [push, dismiss]);

  useEffect(() => () => timers.current?.clear(), []);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 px-4 pb-4 sm:pb-5">
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onClose={() => dismiss(t.id)} onEnter={() => clock().pause(t.id)} onLeave={() => clock().resume(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const STYLE: Record<Kind, { dot: string; label: string }> = {
  success: { dot: "bg-[var(--vt-ok)]", label: "Success" },
  error: { dot: "bg-[var(--vt-blocker)]", label: "Error" },
  warning: { dot: "bg-[var(--vt-warning)]", label: "Warning" },
  info: { dot: "bg-[var(--vt-accent)]", label: "Notice" },
};

function ToastCard({ toast: t, onClose, onEnter, onLeave }: {
  toast: Toast; onClose: () => void; onEnter: () => void; onLeave: () => void;
}) {
  const s = STYLE[t.kind];
  return (
    <div
      role={t.kind === "error" ? "alert" : "status"}
      aria-live={t.kind === "error" ? "assertive" : "polite"}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onFocus={onEnter}
      onBlur={onLeave}
      className={`vt-toast pointer-events-auto relative w-full max-w-[22rem] overflow-hidden rounded-xl border border-line bg-surface/95 shadow-[0_8px_30px_rgba(0,0,0,0.12)] backdrop-blur ${t.leaving ? "vt-toast-out" : "vt-toast-in"}`}
    >
      <div className="flex items-start gap-2.5 py-2.5 pl-3 pr-1.5">
        <span aria-hidden className={`mt-[5px] h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium leading-5"><span className="sr-only">{s.label}: </span>{t.title}</p>
          {t.detail && <p className="truncate text-xs leading-4 text-muted" title={t.detail}>{t.detail}</p>}
        </div>
        <button type="button" onClick={onClose} aria-label="Dismiss notification"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-base leading-none text-muted transition hover:bg-bg hover:text-ink">
          ×
        </button>
      </div>
      <span aria-hidden className={`vt-toast-timer absolute inset-x-0 bottom-0 h-0.5 opacity-60 ${s.dot}`}
        style={{ animationDuration: `${t.duration}ms` }} />
    </div>
  );
}
