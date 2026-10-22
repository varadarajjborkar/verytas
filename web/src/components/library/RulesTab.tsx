"use client";

import { useMemo, useState } from "react";
import { createRule, updateRule } from "@/lib/review-client";
import type { Rule, RuleCategory, RuleDraft } from "@/lib/types";
import { PlusIcon } from "../Icons";
import { useToast } from "../Toaster";
import { RuleCode } from "../ui";
import { Badge, Empty, Field, fromList, toList } from "./parts";
import { SearchField } from "../SearchField";

export const CATEGORIES: RuleCategory[] = ["tone", "terminology", "messaging", "visual", "accessibility", "legal", "claims", "confidentiality"];
const SEVERITY = { must: { label: "Must", tone: "blocker" }, should: { label: "Should", tone: "warning" }, may: { label: "May", tone: "muted" } } as const;
const SEVERITY_ORDER = ["must", "should", "may"];
const STATES = [{ k: "active", l: "Active" }, { k: "draft", l: "Drafts" }, { k: "retired", l: "Retired" }, { k: "all", l: "All" }] as const;
// The matchers a person can configure from a word list. Others (palette, readability) are shown as set.
const TERM_PATTERNS = ["banned_terms", "preferred_terms", "casing"];

/** Rules as one current version per code; editing makes the next version, so old findings keep their citation. */
export function RulesTab({ rules, editable, onChanged, initialState, initialQuery }: {
  rules: Rule[]; editable: boolean; onChanged: () => void; initialState?: string | null; initialQuery?: string | null;
}) {
  const [state, setState] = useState<(typeof STATES)[number]["k"]>(
    () => STATES.find((s) => s.k === initialState)?.k ?? "active");
  const [category, setCategory] = useState<RuleCategory | "all">("all");
  const [query, setQuery] = useState(initialQuery ?? "");
  const [open, setOpen] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  // Only the latest version of each code; earlier ones are history.
  const latest = useMemo(() => {
    const by = new Map<string, Rule>();
    for (const r of rules) if (!by.has(r.code) || by.get(r.code)!.version < r.version) by.set(r.code, r);
    return [...by.values()];
  }, [rules]);
  const shown = latest.filter((r) => (state === "all" || r.status === state) && (category === "all" || r.category === category)
    && (!query.trim() || `${r.code} ${r.title} ${r.text}`.toLowerCase().includes(query.trim().toLowerCase())));
  // Grouped by category in a fixed order, strictest first inside each, so a long library scans by topic.
  const groups = CATEGORIES.map((c) => [c, shown.filter((r) => r.category === c)
    .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) || a.code.localeCompare(b.code))] as const)
    .filter(([, rs]) => rs.length > 0);
  const count = (k: string) => latest.filter((r) => k === "all" || r.status === k).length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Rule status" className="inline-flex rounded-lg bg-sunken p-0.5 text-[13px] font-medium">
          {STATES.map(({ k, l }) => (
            <button key={k} type="button" role="radio" aria-checked={state === k} onClick={() => setState(k)}
              className={`rounded-md px-2.5 py-2 transition ${state === k ? "bg-raised text-ink shadow-[var(--vt-shadow)]" : "text-muted hover:text-ink"}`}>
              {l} <span className="tabular-nums text-subtle">{count(k)}</span>
            </button>
          ))}
        </div>
        <select value={category} onChange={(e) => setCategory(e.target.value as RuleCategory | "all")} aria-label="Category"
          className="vt-input h-9 w-auto py-0 text-[13px]">
          <option value="all">All categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}
        </select>
        <SearchField value={query} onChange={setQuery} placeholder="Search rules by code or words" label="Search rules"
          className="w-full sm:w-72" />
        {editable && (
          <button type="button" onClick={() => setCreating(true)} className="vt-btn vt-btn-primary ml-auto py-1.5">
            <PlusIcon size={14} /> New rule
          </button>
        )}
      </div>

      {creating && <RuleForm onDone={() => { setCreating(false); onChanged(); }} onCancel={() => setCreating(false)} taken={latest.map((r) => r.code)} />}

      {shown.length === 0 ? <Empty>No rules match.</Empty> : (
        <div className="overflow-hidden rounded-xl border border-line bg-raised">
          {groups.map(([cat, rs]) => (
            <section key={cat} aria-label={cat}>
              <h3 className="flex items-baseline gap-2 border-b border-line bg-sunken/50 px-4 py-1.5 text-xs font-semibold capitalize">
                {cat} <span className="font-normal tabular-nums text-subtle">{rs.length}</span>
              </h3>
              <ul>
                {rs.map((r) => (
                  <li key={r.id} className="border-b border-line last:border-0">
                    <button type="button" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-sunken/50">
                      <RuleCode code={r.code} className="hidden w-40 sm:block" />
                      <span className="min-w-0 flex-1">
                        {/* On a phone the title wraps and the source steps aside, so a row reads at a glance. */}
                        <span className="block text-sm font-medium sm:truncate">{r.title}</span>
                        <span className="mt-0.5 block truncate text-xs text-subtle">
                          <span className="font-mono sm:hidden">{r.code} · </span>
                          {r.kind === "deterministic" ? "Checked by rules" : "Judged by the model"}{r.version > 1 ? ` · v${r.version}` : ""}
                          {r.source_ref && <span className="hidden sm:inline"> · {r.source_ref}</span>}
                        </span>
                      </span>
                      <Badge tone={SEVERITY[r.severity].tone}>{SEVERITY[r.severity].label}</Badge>
                      {r.status !== "active" && <Badge tone={r.status === "draft" ? "accent" : "muted"}>{r.status === "draft" ? "Draft" : "Retired"}</Badge>}
                    </button>
                    {open === r.id && <RuleDetail rule={r} editable={editable} onChanged={onChanged} />}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function RuleDetail({ rule, editable, onChanged }: { rule: Rule; editable: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const patch = async (p: Partial<Rule>, done: string) => {
    setBusy(true);
    try {
      await updateRule(rule.id, p);
      toast({ kind: "success", title: done });
      setEditing(false);
      onChanged();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't save the rule", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  };
  if (editing) return <div className="border-t border-line p-4"><RuleEdit rule={rule} busy={busy} onSave={(p) => patch(p, "Saved as a new version")} onCancel={() => setEditing(false)} /></div>;
  return (
    <div className="vt-pop flex flex-col gap-3 border-t border-line px-4 py-4 text-sm">
      <p className="leading-6">{rule.text}</p>
      <PatternView pattern={rule.pattern} />
      {(rule.good_examples.length > 0 || rule.bad_examples.length > 0) && (
        <div className="grid gap-3 md:grid-cols-2">
          {rule.good_examples.length > 0 && <Examples title="On brand" items={rule.good_examples} tone="ok" />}
          {rule.bad_examples.length > 0 && <Examples title="Off brand" items={rule.bad_examples} tone="blocker" />}
        </div>
      )}
      <p className="text-[11px] text-subtle">Visible to {rule.tier} content and above{rule.system ? " · built in" : ""}</p>
      {editable && (
        <div className="flex flex-wrap gap-2">
          {rule.status === "draft" && <button type="button" disabled={busy} onClick={() => patch({ status: "active" }, "Rule is live")} className="vt-btn vt-btn-primary py-1.5">Activate</button>}
          {rule.status === "retired" && <button type="button" disabled={busy} onClick={() => patch({ status: "active" }, "Rule is live again")} className="vt-btn vt-btn-quiet py-1.5">Reactivate</button>}
          {rule.status !== "retired" && <button type="button" disabled={busy} onClick={() => setEditing(true)} className="vt-btn vt-btn-quiet py-1.5">Edit</button>}
          {rule.status !== "retired" && <button type="button" disabled={busy} onClick={() => patch({ status: "retired" }, "Rule retired")} className="vt-btn vt-btn-quiet py-1.5 text-subtle">Retire</button>}
        </div>
      )}
    </div>
  );
}

function Examples({ title, items, tone }: { title: string; items: string[]; tone: "ok" | "blocker" }) {
  return (
    <div className="rounded-lg border border-line p-2.5">
      <p className={`text-[11px] font-semibold ${tone === "ok" ? "text-[var(--vt-ok)]" : "text-[var(--vt-blocker)]"}`}>{title}</p>
      <ul className="mt-1 flex flex-col gap-1 text-xs text-muted">{items.map((x) => <li key={x}>&ldquo;{x}&rdquo;</li>)}</ul>
    </div>
  );
}

function PatternView({ pattern }: { pattern: Record<string, unknown> }) {
  const type = pattern.type as string | undefined;
  if (!type) return null;
  if (type === "preferred_terms" && pattern.map && typeof pattern.map === "object") {
    return (
      <ul className="flex flex-wrap gap-1.5 text-xs">
        {Object.entries(pattern.map as Record<string, string>).map(([wrong, right]) => (
          <li key={wrong} className="rounded-md bg-sunken px-2 py-1"><del className="text-[var(--vt-blocker)]">{wrong}</del> &rarr; <span className="text-[var(--vt-ok)]">{right}</span></li>
        ))}
      </ul>
    );
  }
  if ((type === "banned_terms" || type === "casing") && Array.isArray(pattern.terms)) {
    return (
      <p className="text-xs">
        <span className="mr-1.5 text-muted">{type === "casing" ? "Exact spelling:" : "Never say:"}</span>
        {(pattern.terms as string[]).map((t) => <span key={t} className="mr-1.5 inline-block rounded-md bg-sunken px-2 py-0.5">{t}</span>)}
      </p>
    );
  }
  return <p className="text-xs text-muted">Matcher: <code>{type}</code></p>;
}

/** Word-list editing for the term matchers, plain text for everything else. */
function RuleEdit({ rule, busy, onSave, onCancel }: { rule: Rule; busy: boolean; onSave: (p: Partial<Rule>) => void; onCancel: () => void }) {
  const [title, setTitle] = useState(rule.title);
  const [text, setText] = useState(rule.text);
  const [severity, setSeverity] = useState(rule.severity);
  const [good, setGood] = useState(rule.good_examples.join("\n"));
  const [bad, setBad] = useState(rule.bad_examples.join("\n"));
  const type = rule.pattern.type as string | undefined;
  const termList = rule.kind === "deterministic" && type && TERM_PATTERNS.includes(type);
  const [terms, setTerms] = useState(() => type === "preferred_terms"
    ? Object.entries((rule.pattern.map ?? {}) as Record<string, string>).map(([w, r]) => `${w} => ${r}`).join("\n")
    : fromList(rule.pattern.terms).replaceAll(", ", "\n"));
  const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

  const save = () => {
    const p: Partial<Rule> = {};
    if (title.trim() !== rule.title) p.title = title.trim();
    if (text.trim() !== rule.text) p.text = text.trim();
    if (severity !== rule.severity) p.severity = severity;
    if (lines(good).join("\n") !== rule.good_examples.join("\n")) p.good_examples = lines(good);
    if (lines(bad).join("\n") !== rule.bad_examples.join("\n")) p.bad_examples = lines(bad);
    if (termList) {
      const pattern = type === "preferred_terms"
        ? { type, map: Object.fromEntries(lines(terms).map((l) => l.split(/\s*=>\s*/)).filter((x) => x.length === 2 && x[0] && x[1])) }
        : { ...rule.pattern, terms: lines(terms) };
      if (JSON.stringify(pattern) !== JSON.stringify(rule.pattern)) p.pattern = pattern;
    }
    onSave(p);
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 md:grid-cols-[1fr_9rem]">
        <Field label="Title"><input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className="vt-input" /></Field>
        <Field label="Severity">
          <select value={severity} onChange={(e) => setSeverity(e.target.value as Rule["severity"])} className="vt-input">
            <option value="must">Must</option><option value="should">Should</option><option value="may">May</option>
          </select>
        </Field>
      </div>
      <Field label="Rule"><textarea value={text} onChange={(e) => setText(e.target.value)} className="vt-input min-h-20" /></Field>
      {termList && (
        <Field label={type === "preferred_terms" ? "Swaps" : "Terms"} hint={type === "preferred_terms" ? "one per line: wrong => right" : "one per line"}>
          <textarea value={terms} onChange={(e) => setTerms(e.target.value)} className="vt-input min-h-20 font-mono text-xs" />
        </Field>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="On-brand examples" hint="one per line"><textarea value={good} onChange={(e) => setGood(e.target.value)} className="vt-input min-h-16 text-xs" /></Field>
        <Field label="Off-brand examples" hint="one per line"><textarea value={bad} onChange={(e) => setBad(e.target.value)} className="vt-input min-h-16 text-xs" /></Field>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" disabled={busy || !title.trim() || !text.trim()} onClick={save} className="vt-btn vt-btn-primary py-1.5">Save as new version</button>
        <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet py-1.5">Cancel</button>
        <span className="text-[11px] text-subtle">Past findings keep citing the version they were judged against.</span>
      </div>
    </div>
  );
}

/** A new rule from scratch: a model-judged rule by default, or a word list the checker matches exactly. */
function RuleForm({ onDone, onCancel, taken }: { onDone: () => void; onCancel: () => void; taken: string[] }) {
  const [draft, setDraft] = useState({ code: "", category: "tone" as RuleCategory, severity: "should" as Rule["severity"],
    title: "", text: "", matcher: "semantic", terms: "", source_ref: "", tier: "public" as Rule["tier"] });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (p: Partial<typeof draft>) => setDraft((d) => ({ ...d, ...p }));
  const code = draft.code.trim().toUpperCase();
  const codeOk = /^[A-Z][A-Z0-9-]{1,39}$/.test(code) && !taken.includes(code);

  async function save() {
    setBusy(true);
    const lines = draft.terms.split("\n").map((x) => x.trim()).filter(Boolean);
    const pattern = draft.matcher === "semantic" ? {}
      : draft.matcher === "preferred_terms"
        ? { type: "preferred_terms", map: Object.fromEntries(lines.map((l) => l.split(/\s*=>\s*/)).filter((x) => x.length === 2)) }
        : { type: draft.matcher, terms: toList(draft.terms) };
    const rule: RuleDraft = {
      code, category: draft.category, kind: draft.matcher === "semantic" ? "semantic" : "deterministic", severity: draft.severity,
      title: draft.title.trim(), text: draft.text.trim(), good_examples: [], bad_examples: [], pattern,
      source_ref: draft.source_ref.trim() || null, tier: draft.tier,
    };
    try {
      await createRule(rule);
      toast({ kind: "success", title: "Draft rule added", detail: "Activate it to use it in reviews." });
      onDone();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't add the rule", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="vt-pop vt-card flex flex-col gap-3 p-4" aria-label="New rule">
      <div className="grid gap-3 md:grid-cols-4">
        <Field label="Code" hint={draft.code && !codeOk ? "taken or invalid" : "e.g. TONE-4"}>
          <input value={draft.code} onChange={(e) => set({ code: e.target.value })} className="vt-input font-mono uppercase" />
        </Field>
        <Field label="Category">
          <select value={draft.category} onChange={(e) => set({ category: e.target.value as RuleCategory })} className="vt-input capitalize">
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Severity">
          <select value={draft.severity} onChange={(e) => set({ severity: e.target.value as Rule["severity"] })} className="vt-input">
            <option value="must">Must</option><option value="should">Should</option><option value="may">May</option>
          </select>
        </Field>
        <Field label="How it's checked">
          <select value={draft.matcher} onChange={(e) => set({ matcher: e.target.value })} className="vt-input">
            <option value="semantic">Judged by the model</option>
            <option value="banned_terms">Never say these words</option>
            <option value="preferred_terms">Say this, not that</option>
            <option value="casing">Exact spelling and casing</option>
          </select>
        </Field>
      </div>
      <Field label="Title"><input value={draft.title} onChange={(e) => set({ title: e.target.value })} maxLength={200} className="vt-input" /></Field>
      <Field label="Rule" hint="as you would explain it to a new writer">
        <textarea value={draft.text} onChange={(e) => set({ text: e.target.value })} className="vt-input min-h-16" />
      </Field>
      {draft.matcher !== "semantic" && (
        <Field label={draft.matcher === "preferred_terms" ? "Swaps" : "Terms"} hint={draft.matcher === "preferred_terms" ? "one per line: wrong => right" : "one per line"}>
          <textarea value={draft.terms} onChange={(e) => set({ terms: e.target.value })} className="vt-input min-h-16 font-mono text-xs" />
        </Field>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Source" hint="optional"><input value={draft.source_ref} onChange={(e) => set({ source_ref: e.target.value })} placeholder="Brand book p.12" className="vt-input" /></Field>
        <Field label="Applies to">
          <select value={draft.tier} onChange={(e) => set({ tier: e.target.value as Rule["tier"] })} className="vt-input">
            <option value="public">All content</option><option value="internal">Internal and confidential</option><option value="confidential">Confidential only</option>
          </select>
        </Field>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" disabled={busy || !codeOk || !draft.title.trim() || !draft.text.trim() || (draft.matcher !== "semantic" && !draft.terms.trim())}
          onClick={save} className="vt-btn vt-btn-primary py-1.5">Add as draft</button>
        <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet py-1.5">Cancel</button>
      </div>
    </section>
  );
}
