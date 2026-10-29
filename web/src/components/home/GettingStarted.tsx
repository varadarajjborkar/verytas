"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getOnboarding, loadSampleKit } from "@/lib/review-client";
import { useStored, writeStored } from "@/lib/stored";
import type { Onboarding, OnboardingStep } from "@/lib/types";
import { ArrowRightIcon, CheckIcon, CloseIcon, InfoIcon } from "../Icons";
import { OPEN_SETTINGS } from "../SettingsMenu";
import { useToast } from "../Toaster";
import { useViewer } from "../Viewer";
import { shownError } from "@/lib/errors";

// One line on what this person's side of Verytas is for, so the checklist below reads as a path, not chores.
const INTRO: Record<string, string> = {
  brand_admin: "You keep the brand library. Every review checks posts against it, and nothing enters it without you.",
  creator: "Write as you always do. Verytas checks each piece against the brand's guidelines before the brand team sees it.",
  reviewer: "Pieces reach you already checked. You decide on what Verytas found, and your decisions make it sharper.",
  approver: "Pieces reach you already checked. You decide on what Verytas found and approve what is ready to go out.",
  auditor: "You can read every review, decision and library change, each recorded in a tamper-evident log.",
};

/**
 * The first-sign-in walkthrough: what this role does here, the steps that make the workspace useful (each
 * ticked from what the workspace really holds), a sample brand kit for an empty library, and a plain note on
 * what in this demo is synthetic. Hidden once everything is done or the person closes it.
 */
export function GettingStarted() {
  const { me } = useViewer();
  const [data, setData] = useState<Onboarding | null>(null);
  const [loading, setLoading] = useState(false);
  const toast = useToast();
  const router = useRouter();
  const key = `vt-getting-started:${me?.id ?? "anon"}`;
  const closed = useStored(key) === "closed";

  const load = useCallback(() => getOnboarding().then(setData).catch(() => setData(null)), []);
  useEffect(() => {
    if (me) void load();
  }, [me, load]);

  if (!me || !data || closed) return null;
  const done = data.steps.filter((s) => s.done).length;
  if (done === data.steps.length && !data.sample_kit) return null;

  async function sample() {
    setLoading(true);
    try {
      const made = await loadSampleKit();
      toast({ kind: "success", title: "Sample brand kit loaded",
        detail: `${made.rules} rules, ${made.facts} facts, ${made.terms} codenames and ${made.assets} pieces of artwork` });
      await load();
      router.refresh();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't load the sample kit", detail: shownError(err) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="getting-started" className="vt-card relative mb-5 p-4 md:p-5">
      <button type="button" onClick={() => writeStored(key, "closed")} aria-label="Hide getting started"
        title="Hide" className="absolute right-3 top-3 grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
        <CloseIcon size={16} />
      </button>
      <div className="pr-10">
        <p className="text-xs font-medium text-muted">Getting started at {data.company}</p>
        <h2 id="getting-started" className="mt-1 text-base font-semibold">Welcome, {me.name.split(/\s+/)[0]}</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">{INTRO[data.role] ?? INTRO.reviewer}</p>
      </div>

      {data.steps.length > 0 && (
        <>
          <div className="mt-4 flex items-center gap-3" aria-hidden>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken">
              <div className="h-full rounded-full bg-accent transition-[width] duration-500"
                style={{ width: `${(100 * done) / data.steps.length}%` }} />
            </div>
            <span className="text-xs tabular-nums text-muted">{done} of {data.steps.length}</span>
          </div>
          <ol className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {data.steps.map((s, i) => <StepRow key={s.key} step={s} n={i + 1} />)}
          </ol>
        </>
      )}

      {data.sample_kit && (
        <div className="mt-4 flex flex-col gap-3 rounded-xl border border-line bg-sunken/60 p-3.5 sm:flex-row sm:items-center">
          <p className="flex-1 text-sm text-muted">
            <span className="font-medium text-ink">No material to hand?</span> Load a sample brand kit: the library of
            Kitepath, a fictional learning app, with its rules, facts, codenames, contacts and logos. You can edit or
            retire any of it later, and it loads only while your library is empty.
          </p>
          <button type="button" onClick={sample} disabled={loading} className="vt-btn vt-btn-primary vt-btn-sm shrink-0">
            {loading ? "Loading…" : "Load sample kit"}
          </button>
        </div>
      )}

      <p className="mt-4 flex gap-2 border-t border-line pt-3 text-xs leading-5 text-subtle">
        <InfoIcon size={14} className="mt-0.5 shrink-0" />
        <span>
          About this demo: the companies, people and history here are synthetic, made to show how Verytas works.
          {data.self_serve && data.role === "brand_admin" ? " Your own company starts empty, apart from the built-in checks." : ""} In production the
          library is filled from a brand&apos;s own systems (DAM, Drive, CMS or SAP exports, or read-only links) through the
          same Intake step, and reviewed by the brand team before anything is used.
        </span>
      </p>
    </section>
  );
}

function StepRow({ step, n }: { step: OnboardingStep; n: number }) {
  const body = (
    <>
      <span aria-hidden className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-[11px] font-semibold ${step.done
        ? "bg-accent text-white" : "border border-line text-muted"}`}>
        {step.done ? <CheckIcon size={12} strokeWidth={3} /> : n}
      </span>
      <span className="min-w-0 flex-1">
        <span className={`block text-sm font-medium ${step.done ? "text-muted line-through decoration-line" : ""}`}>
          {step.title}<span className="sr-only">{step.done ? " (done)" : ""}</span>
        </span>
        <span className="mt-0.5 block text-xs leading-5 text-subtle">{step.detail}</span>
      </span>
      {!step.done && <ArrowRightIcon size={14} className="mt-1 shrink-0 text-subtle transition group-hover:translate-x-0.5 group-hover:text-accent" />}
    </>
  );
  const cls = "group flex h-full items-start gap-2.5 rounded-xl p-2.5 text-left transition hover:bg-sunken";
  return (
    <li>
      {step.href ? (
        <Link href={step.href} className={cls}>{body}</Link>
      ) : (
        // The join code lives in Settings; the step opens it there instead of repeating it here.
        <button type="button" className={`${cls} w-full`}
          onClick={() => window.dispatchEvent(new CustomEvent(OPEN_SETTINGS, { detail: "profile" }))}>{body}</button>
      )}
    </li>
  );
}
