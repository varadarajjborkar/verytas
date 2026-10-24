// Shared by the /api/assist route and the Summarize panel: the shape of a brief, and the clean-up that
// makes model text safe and pleasant to show. No server-only imports, so the browser can use it too.

export const NEXT_ACTIONS = ["approve", "send_back", "escalate_to_legal", "ask_creator"] as const;
export type NextAction = (typeof NEXT_ACTIONS)[number];

export const NEXT_LABEL: Record<NextAction, string> = {
  approve: "Approve",
  send_back: "Send back to the creator",
  escalate_to_legal: "Escalate to legal",
  ask_creator: "Ask the creator",
};

export type Brief = {
  tldr: string;
  blocking: { rule: string | null; issue: string; why: string }[];
  minor: { rule: string | null; issue: string }[];
  creator_side: string;
  history: string[];
  suggested_next_step: { action: NextAction | null; reason: string };
  /** What to ask the creator for: requests, not questions for Verytas. */
  ask_creator: string[];
  /** What the manager could ask Verytas next about this item, written from its data. */
  follow_ups: string[];
  risk_if_published: string;
};

export type AssistKind = "content" | "escalation";

/** Em and en dashes read as machine prose and are not allowed in this product's text; the prompt asks
 * the model not to write them and this catches the ones that slip through. */
export function plainText(s: string): string {
  return s.replace(/\s*[\u2013\u2014]\s*/g, ", ").replace(/\u2212/g, "-");
}

/** Hidden terms arrive as [[TERM_1]]; the manager sees them as a labelled blank rather than markup. */
export function readable(s: string): string {
  return s.replace(/\[\[TERM_(\d+)\]\]/g, "[confidential term $1]");
}

const BRIEF_ITEMS = 3;
const str = (v: unknown, max = 1200): string => (typeof v === "string" ? plainText(v).trim().slice(0, max) : "");
const list = (v: unknown, max: number): unknown[] => (Array.isArray(v) ? v.slice(0, max) : []);

function actionOf(v: unknown): NextAction | null {
  const s = (typeof v === "string" ? v : "").toLowerCase().replace(/[\s-]+/g, "_");
  if ((NEXT_ACTIONS as readonly string[]).includes(s)) return s as NextAction;
  if (s.includes("legal")) return "escalate_to_legal";
  if (s.includes("approve")) return "approve";
  if (s.includes("send") || s.includes("back") || s.includes("change")) return "send_back";
  if (s.includes("ask") || s.includes("creator")) return "ask_creator";
  return null;
}

/** Turns whatever the model returned into a Brief, or null when it isn't a brief at all (no summary line).
 * Missing optional parts become empty rather than failing the whole thing. */
export function normalizeBrief(raw: unknown): Brief | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const tldr = str(r.tldr, 600);
  if (!tldr) return null;
  const entry = (v: unknown) => {
    if (typeof v === "string") return { rule: null, issue: str(v), why: "" };
    const o = (v ?? {}) as Record<string, unknown>;
    return { rule: str(o.rule, 60) || null, issue: str(o.issue ?? o.title ?? o.what, 400), why: str(o.why ?? o.why_it_matters ?? o.reason, 600) };
  };
  const texts = (v: unknown, max: number) => list(v, max).map((x) => str(x, 400)).filter(Boolean);
  const step = (r.suggested_next_step ?? {}) as Record<string, unknown>;
  const stepObj = typeof r.suggested_next_step === "string" ? { action: r.suggested_next_step, reason: "" } : step;
  return {
    tldr,
    // The prompt asks for three of each; a model that writes more still gets a short brief. The keys are
    // named the way the panel reads ("must change") so the model doesn't echo "blocking" into the text;
    // the older names are still read.
    blocking: list(r.must_change ?? r.blocking, BRIEF_ITEMS).map(entry).filter((e) => e.issue),
    minor: list(r.worth_a_look ?? r.minor, BRIEF_ITEMS).map(entry).filter((e) => e.issue).map(({ rule, issue }) => ({ rule, issue })),
    creator_side: str(r.creator_side, 1200),
    history: texts(r.history, BRIEF_ITEMS),
    suggested_next_step: { action: actionOf(stepObj.action), reason: str(stepObj.reason ?? stepObj.why, 600) },
    ask_creator: texts(r.ask_creator ?? r.questions_to_ask, 2),
    follow_ups: texts(r.follow_ups, 4).map((q) => q.slice(0, 90)),
    risk_if_published: str(r.risk_if_published, 800),
  };
}

/** The first JSON object in a model reply, which may be wrapped in a code fence or a sentence. */
export function parseBrief(content: string): Brief | null {
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    return normalizeBrief(JSON.parse(content.slice(start, end + 1)));
  } catch {
    return null;
  }
}

/** Follow-ups are short, plain questions: the prompt asks for under 60 characters. */
const FOLLOW_UP_CHARS = 70;
const FOLLOW_UPS_MAX = 3;

/**
 * A chat answer and the follow-up questions the model put on its last line (">> a | b | c"). Only the final
 * line counts: a ">>" earlier in the text is part of the answer (quoted mail, a creator's own wording echoed
 * back) and must neither cut it short nor become a button. The marker line is never shown, and a lone ">"
 * on the last line is held back too, so the marker does not flash while it streams in.
 *
 * Buttons send their text as the manager's own message, so a candidate that is not short plain text (links,
 * markup) or that merely repeats words of the answer itself is dropped.
 */
export function splitFollowUps(text: string): { body: string; followUps: string[] } {
  const trimmed = text.trimEnd();
  const start = trimmed.lastIndexOf("\n") + 1;
  const marker = /^\s*(?:>>\s*(.*)|>)$/.exec(trimmed.slice(start));
  if (!marker) return { body: text, followUps: [] };
  const body = trimmed.slice(0, start).trimEnd();
  const seen = new Set<string>();
  const followUps = (marker[1] ?? "").split("|").map((q) => q.replace(/\s+/g, " ").trim()).filter((q) => {
    const key = q.toLowerCase();
    if (q.length <= 3 || q.length > FOLLOW_UP_CHARS || /[<>`[\]{}]|https?:|www\./i.test(q)) return false;
    if (seen.has(key) || body.toLowerCase().includes(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, FOLLOW_UPS_MAX);
  return { body, followUps };
}
