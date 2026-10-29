// Browser-side calls for the review workspace. Everything goes through the
// server proxy (app/api/v), which holds the API token and an allowlist.

import type {
  ApprovedPerson, BrandAsset, BrandEvent, ContentDetail, CreatorRow, CreatorTrack, EscalationRequest, EventImpact, PublicContact, ContentRow, ContentStatus, Decision, Dispute, Fact, Finding, Level, Me, Person, Precheck,
  IntakeBatch, IntakeBatchDetail, IntakeDraft, IntakeItem, IntakeItemIn, Onboarding, SampleKit,
  Mark, PerformanceReport, PersonalToken, CreatedToken, PinnedComment, PostMetrics, PostResult, Review, Rule, RuleClarification, RuleDraft, SearchHit, Term, Timeline, UploadedMedia,
} from "./types";
import { GENERIC_MESSAGE, isSafeMessage, NETWORK_MESSAGE, statusMessage } from "./errors";

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

/** The console's own answer when no API is configured (app/api/v, `demo: true`): the only 503 that means "run on
 * sample data". Any other 503 is the API busy or restarting, which must never switch a screen to demo mode. */
export const isOffline = (err: unknown): boolean => err instanceof ApiError && err.status === 503
  && (err.detail as { demo?: unknown } | null | undefined)?.demo === true;

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v/${path}`, init);
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, NETWORK_MESSAGE);
  }
  const text = await res.text().catch(() => "");
  let json: unknown = null;
  let parsed = true;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    parsed = false; // a gateway's or proxy's page, not ours: never shown, never read as data
  }
  if (!res.ok) {
    const j = (parsed ? json : null) as { error?: string; detail?: unknown } | null;
    const detail = j?.detail;
    // FastAPI's validation errors are a list of { loc, msg }; a field validator's own words follow "Value error, ".
    const listed = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d?.msg?.replace(/^Value error, /, "")).filter(Boolean).join("; ")
      : "";
    const own = typeof detail === "string" ? detail : listed || ((detail as { message?: string })?.message ?? j?.error);
    throw new ApiError(res.status, isSafeMessage(own) ? own : statusMessage(res.status), parsed ? detail ?? json : undefined);
  }
  if (!parsed) throw new ApiError(res.status, GENERIC_MESSAGE);
  return json as T;
}

export const json = (body: unknown): RequestInit => ({
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

// Prism Intake: hand over material, answer what it asks, approve what reads right.
export async function intakeUpload(file: File): Promise<{ id: string; name: string | null; media_type: string; bytes: number }> {
  const form = new FormData();
  form.append("file", file);
  return api("intake/files", { method: "POST", body: form });
}
export const startIntake = (body: { note?: string; tier?: string; items: IntakeItemIn[] }) =>
  api<{ id: number; status: string }>("intake", json(body));
export const listIntake = () => api<IntakeBatch[]>("intake");
export const getIntake = (id: number) => api<IntakeBatchDetail>(`intake/${id}`);
export const answerIntake = (itemId: number, context: string) => api<IntakeItem>(`intake/items/${itemId}/answer`, json({ context }));
export const refreshIntake = (itemId: number) => api<IntakeItem>(`intake/items/${itemId}/refresh`, json({}));
export const decideDraft = (id: number, action: "approve" | "reject", payload?: Record<string, unknown>) =>
  api<IntakeDraft>(`intake/drafts/${id}`, json({ action, payload }));
export const decideDrafts = (batchId: number, ids: number[], action: "approve" | "reject" = "approve") =>
  api<{ done: number[]; skipped: number[]; pending: number }>(`intake/${batchId}/decide`, json({ ids, action }));

type SubmitOut = { content: { id: number }; version: { id: number; version_no: number; body: string }; review_id: number };
export const submit = (body: unknown) => api<SubmitOut>("contents", json(body));
export const getReview = (id: number) => api<Review>(`reviews/${id}`);
export const listDisputes = (contentId: number) => api<Dispute[]>(`contents/${contentId}/disputes`);
export type ReviewNews = { unread: number; pieces: { content_id: number; title: string; status: string; at: string }[] };
export const reviewUpdates = () => api<ReviewNews>("me/review-updates");
export const markSeen = (contentId: number) => api<null>(`contents/${contentId}/seen`, { method: "POST" });
export const fileDispute = (findingId: number, claim: string, language: string | null) =>
  api<Dispute>(`findings/${findingId}/disputes`, json({ claim, language }));
export const resubmit = (contentId: number, body: unknown) =>
  api<{ submit: SubmitOut; disputes: number[]; applied: number; skipped: string[] }>(`contents/${contentId}/resubmit`,
    json(body));
export const listContents = (mine: boolean) => api<ContentRow[]>(`contents${mine ? "?mine=true" : ""}`);
export const getTimeline = (contentId: number) => api<Timeline>(`contents/${contentId}/timeline`);
export const addComment = (contentId: number, body: string, versionId?: number, parentId?: number) =>
  api<{ id: number }>(`contents/${contentId}/comments`, json({ body, version_id: versionId ?? null, parent_id: parentId ?? null }));
export const decide = (findingId: number, action: Decision["action"], reasonCode?: string | null, reasonText?: string | null) =>
  api<Decision>(`findings/${findingId}/decision`, json({ action, reason_code: reasonCode ?? null, reason_text: reasonText || null }));
export const listPeople = () => api<Person[]>("users");

// Personal tokens for the person's own AI client (the /mcp endpoint). Creating one returns the secret once.
export const listTokens = () => api<PersonalToken[]>("me/tokens");
export const createToken = (name: string, scopes: ("read" | "write")[], days: number) =>
  api<CreatedToken>("me/tokens", json({ name, scopes, days }));
export const revokeToken = (id: number) => api<null>(`me/tokens/${id}`, { method: "DELETE" });

// --- escalations, events, public contacts ---
export const escalate = (findingId: number, message: string) =>
  api<EscalationRequest>(`findings/${findingId}/escalations`, json({ message }));
export const listEscalations = (state: "open" | "resolved" | "all" = "open", contentId?: number) =>
  api<EscalationRequest[]>(`escalations?state=${state}${contentId ? `&content_id=${contentId}` : ""}`);
export const resolveEscalation = (id: number, outcome: "upheld" | "cleared", reasonCode?: string | null, note?: string | null) =>
  api<EscalationRequest>(`escalations/${id}/resolve`, json({ outcome, reason_code: reasonCode ?? null, note: note || null }));
export const countEscalations = () => api<{ open: number }>("escalations/count");
export const withdrawEscalation = (id: number) => api<EscalationRequest>(`escalations/${id}/withdraw`, json({}));
export const listEvents = () => api<BrandEvent[]>("events");
export const listCreators = () => api<CreatorRow[]>("insights/creators");
export const creatorTrack = (id: number) => api<CreatorTrack>(`insights/creators/${id}`);
export const createEvent = (e: Partial<BrandEvent>) => api<BrandEvent>("events", json(e));
export const updateEvent = (id: number, e: Partial<BrandEvent>) => api<BrandEvent>(`events/${id}`, send("PATCH", e));
export const cancelEvent = (id: number) => api<BrandEvent>(`events/${id}/cancel`, json({}));
export const eventImpacts = (id: number) => api<EventImpact[]>(`events/${id}/impacts`);
export const listContacts = () => api<PublicContact[]>("public-contacts");
export const addContact = (c: Partial<PublicContact>) => api<PublicContact>("public-contacts", json(c));
export const retireContact = (id: number) => api<null>(`public-contacts/${id}`, send("DELETE"));
export const listApproved = () => api<ApprovedPerson[]>("people");
export const addApproved = (p: Record<string, unknown>) => api<ApprovedPerson>("people", json(p));
export const patchApproved = (id: number, p: Record<string, unknown>) =>
  api<ApprovedPerson>(`people/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });
export const addReference = (id: number, ref: { media_type: string; data_base64: string }) =>
  api<ApprovedPerson["references"][number]>(`people/${id}/references`, json({ ...ref, source: "upload" }));
export const removeReference = (id: number, refId: number) => api<null>(`people/${id}/references/${refId}`, send("DELETE"));
export const referenceUrl = (id: number, refId: number) => `/api/v/people/${id}/references/${refId}/image`;

// --- the brand library (writes are brand-admin only; the API enforces it) ---
const send = (method: string, body?: unknown): RequestInit => ({
  method, headers: body === undefined ? undefined : { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});
export const listRules = () => api<Rule[]>("rules");
export const createRule = (rule: RuleDraft) => api<Rule>("rules", json(rule));
export const updateRule = (id: number, patch: Partial<Rule>) => api<Rule>(`rules/${id}`, send("PATCH", patch));
export const getOnboarding = () => api<Onboarding>("onboarding");
export const loadSampleKit = () => api<SampleKit>("onboarding/sample-kit", json({}));
export const clarifyRule = (id: number) => api<RuleClarification>(`rules/${id}/clarify`, json({}));
export const extractRules = (input: { text?: string; blob_id?: string; source_ref?: string }) =>
  api<{ rules: RuleDraft[]; notes: string[]; model: string }>("rules/extract", json(input));
export const listFacts = () => api<Fact[]>("facts");
export const createFact = (fact: Partial<Fact>) => api<Fact>("facts", json(fact));
export const retireFact = (id: number) => api<Fact>(`facts/${id}/retire`, json({}));
export const listTerms = () => api<Term[]>("confidential-terms");
export const createTerm = (term: Partial<Term>) => api<Term>("confidential-terms", json(term));
export const updateTerm = (id: number, patch: Partial<Term>) => api<Term>(`confidential-terms/${id}`, send("PATCH", patch));
export const deleteTerm = (id: number) => api<null>(`confidential-terms/${id}`, send("DELETE"));
export const listAssets = () => api<BrandAsset[]>("brand-assets");
export const createAsset = (asset: Record<string, unknown>) => api<BrandAsset>("brand-assets", json(asset));
export const retireAsset = (id: number) => api<null>(`brand-assets/${id}`, send("DELETE"));
export const assetImageUrl = (id: number) => `/api/v/brand-assets/${id}/image`;
export const versionImageUrl = (contentId: number, versionId: number, imageId: string) =>
  `/api/v/contents/${contentId}/versions/${versionId}/images/${encodeURIComponent(imageId)}`;
export const versionVideoUrl = (contentId: number, versionId: number, videoId: string) =>
  `/api/v/contents/${contentId}/versions/${versionId}/videos/${encodeURIComponent(videoId)}`;
export const getResult = (contentId: number) => api<PostResult | null>(`contents/${contentId}/result`);
export const saveResult = (contentId: number, body: { url: string; posted_on: string | null; metrics: PostMetrics }) =>
  api<PostResult>(`contents/${contentId}/result`, send("PUT", body));
export const removeResult = (contentId: number) => api<null>(`contents/${contentId}/result`, send("DELETE"));
export const importResults = (csv: string) =>
  api<{ updated: number; skipped: { row: number; reason: string }[]; skipped_total: number }>("results/import", json({ csv }));
export const performanceReport = () => api<PerformanceReport>("insights/performance");
export const listComments = (contentId: number) => api<PinnedComment[]>(`contents/${contentId}/comments`);
/** A comment pinned to a stretch of a video or drawn onto an image. */
export const addPinnedComment = (contentId: number, pin: {
  body: string; version_id: number; media_id: string; time_start?: number; time_end?: number; marks?: Mark[];
}) => api<PinnedComment>(`contents/${contentId}/comments`, json(pin));
export type DocumentPreview =
  | { kind: "pages"; pages: { width: number; height: number }[]; total_pages: number;
      marks: { finding_id: number; page: number; box: number[] }[] }
  | { kind: "html"; html: string };
const docPath = (contentId: number, versionId: number, docId: string) =>
  `contents/${contentId}/versions/${versionId}/documents/${encodeURIComponent(docId)}`;
export const getDocumentPreview = (contentId: number, versionId: number, docId: string) =>
  api<DocumentPreview>(`${docPath(contentId, versionId, docId)}/preview`);
export const documentPageUrl = (contentId: number, versionId: number, docId: string, page: number) =>
  `/api/v/${docPath(contentId, versionId, docId)}/pages/${page}`;
export const getContent = (id: number) => api<ContentDetail>(`contents/${id}`);
export const getMe = () => api<Me>("me");
/** The global search. `limit` is hits per group; an empty query returns the caller's suggestions. Abort stale calls with `signal`. */
export const search = (q: string, limit = 5, signal?: AbortSignal) =>
  api<{ query: string; results: SearchHit[] }>(`search?q=${encodeURIComponent(q)}&limit=${limit}`, { signal });
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
/** What each status means, for a first-time reader: shown on hover wherever the status is. */
export const STATUS_HINT: Record<ContentStatus, string> = {
  draft: "Still being written. The brand team isn't asked to decide until the creator sends it.",
  in_review: "Sent by the creator and waiting for the brand team to decide.",
  changes_requested: "The brand team sent it back with changes to make.",
  approved: "The brand team approved it. It can go out.",
  published: "Approved and posted.",
  withdrawn: "Taken back by the creator or an approver; it won't go out.",
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
  if (src === "body") return "In the text";
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
    // Slides and sheets are pages to the API; the locator says what people call them.
    const page = loc.label ?? parts[2]?.replace("p", "page ");
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
