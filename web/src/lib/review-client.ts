// Browser-side calls for the review workspace. Everything goes through the
// server proxy (app/api/v), which holds the API token and an allowlist.

import type { ContentDetail, ContentRow, ContentStatus, Dispute, Finding, Level, Me, Precheck, Review, UploadedMedia } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/v/${path}`, init);
  const text = await res.text();
  let json: unknown = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = { error: text.slice(0, 200) };
  }
  if (!res.ok) {
    const j = json as { error?: string; detail?: unknown };
    const detail = j?.detail;
    const message = typeof detail === "string" ? detail
      : (detail as { message?: string })?.message ?? j?.error ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, message, detail ?? json);
  }
  return json as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function upload(file: File): Promise<UploadedMedia> {
  const form = new FormData();
  form.append("file", file);
  return api<UploadedMedia>("media", { method: "POST", body: form });
}

export const precheck = (body: unknown) => api<Precheck>("contents/precheck", json(body));

type SubmitOut = { content: { id: number }; version: { id: number; version_no: number; body: string }; review_id: number };
export const submit = (body: unknown) => api<SubmitOut>("contents", json(body));
export const getReview = (id: number) => api<Review>(`reviews/${id}`);
export const listDisputes = (contentId: number) => api<Dispute[]>(`contents/${contentId}/disputes`);
export const resubmit = (contentId: number, body: unknown) =>
  api<{ submit: SubmitOut; disputes: number[]; applied: number; skipped: string[] }>(`contents/${contentId}/resubmit`,
    json(body));
export const listContents = (mine: boolean) => api<ContentRow[]>(`contents${mine ? "?mine=true" : ""}`);
export const getContent = (id: number) => api<ContentDetail>(`contents/${id}`);
export const getMe = () => api<Me>("me");
export const transition = (contentId: number, to: ContentStatus, note?: string, override = false) =>
  api<ContentRow>(`contents/${contentId}/transition`, json({ to, note: note || null, override_blockers: override }));
export const aiEdit = (contentId: number, instruction: string) =>
  api<{ body: string; changes: string[]; remaining: string[]; model: string }>(`contents/${contentId}/ai-edit`,
    json({ instruction }));

/** Poll until the review finishes. Multimodal reviews (video, long PDFs) can take a minute or more. */
/** Polls until the review finishes. Abort the signal when nobody is watching any more. */
export async function waitForReview(id: number, onTick?: (seconds: number) => void, signal?: AbortSignal,
  limitS = 600): Promise<Review> {
  const started = Date.now();
  for (let delay = 700; ; delay = Math.min(delay * 1.4, 3000)) {
    signal?.throwIfAborted();
    const review = await getReview(id);
    if (review.status === "done" || review.status === "failed") return review;
    const elapsed = (Date.now() - started) / 1000;
    if (elapsed > limitS) throw new Error("The review is taking unusually long. It is still running; reload later.");
    onTick?.(Math.round(elapsed));
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, delay);
      signal?.addEventListener("abort", () => { clearTimeout(t); reject(signal.reason); }, { once: true });
    });
  }
}

// --- presentation helpers -------------------------------------------------------------------

export const STATUS_LABEL: Record<ContentStatus, string> = {
  draft: "Draft",
  in_review: "In review",
  changes_requested: "Changes requested",
  approved: "Approved",
  published: "Published",
  withdrawn: "Withdrawn",
};
/** Finished pieces: shown struck through in the history, and read-only once published or withdrawn. */
export const FINISHED: ContentStatus[] = ["approved", "published", "withdrawn"];

/** The next steps a person may take from a status (mirrors the API's _TRANSITIONS and its
 * withdraw rule, so nothing is offered that would be refused; the API still decides). */
export function nextSteps(status: ContentStatus, role: string, author: boolean): { to: ContentStatus; label: string; primary?: boolean }[] {
  const admin = role === "brand_admin";
  const approver = admin || role === "approver";
  const reviewer = approver || role === "reviewer";
  const submitter = reviewer || role === "creator";
  const steps: { to: ContentStatus; label: string; primary?: boolean }[] = [];
  if ((status === "draft" || status === "changes_requested") && submitter) steps.push({ to: "in_review", label: "Send for approval", primary: true });
  if (status === "in_review" && approver) steps.push({ to: "approved", label: "Approve", primary: true });
  if (status === "in_review" && reviewer) steps.push({ to: "changes_requested", label: "Request changes" });
  if (status === "approved" && approver) steps.push({ to: "published", label: "Mark published", primary: true });
  if (status === "approved" && approver) steps.push({ to: "changes_requested", label: "Request changes" });
  if (status !== "published" && status !== "withdrawn" && (author || approver)) steps.push({ to: "withdrawn", label: "Withdraw" });
  return steps;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString([], { day: "numeric", month: "short" });
}

export const PRIORITY: Record<Level, { code: string; label: string }> = {
  blocker: { code: "P1", label: "Must fix" },
  warning: { code: "P2", label: "Should fix" },
  advisory: { code: "P3", label: "Consider" },
};

const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** Where a finding lives, in words a creator recognises. */
export function whereLabel(f: Pick<Finding, "source" | "locator">): string {
  const src = f.source ?? "body";
  const loc = f.locator ?? {};
  const time = loc.time ? ` at ${fmtTime(loc.time[0])}` : "";
  if (src === "body") return "Caption / text";
  if (src === "intake") return "The upload itself";
  if (src === "disclosure") return "Whole post";
  const parts = src.split(":");
  if (parts[0] === "img") {
    const name = parts[1];
    if (parts[2] === "ocr") return `Text in image “${name}”`;
    if (parts[2] === "vision-text") return `Text in image “${name}” (read by vision model)`;
    return `Image “${name}”`;
  }
  if (parts[0] === "doc") {
    const page = parts[2]?.replace("p", "page ");
    if (parts[3] === "text") return `${parts[1]} · ${page}`;
    if (parts[3] === "scan") return `${parts[1]} · ${page} (scanned)`;
    if (parts[3]?.startsWith("img")) return `${parts[1]} · ${page} · picture ${parts[3].slice(3)}`;
    return `${parts[1]} · ${page}`;
  }
  if (parts[0] === "vid") {
    const what = { captions: "on-screen text", speech: "speech", subtitles: "subtitles" }[parts[2] ?? ""] ?? "frames";
    return `Video “${parts[1]}” · ${what}${time}`;
  }
  return src;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
