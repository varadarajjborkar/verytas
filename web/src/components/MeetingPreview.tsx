"use client";

import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useModalFocus } from "./Drawer";
import { CalendarIcon, ChatIcon, CheckIcon, CloseIcon, PhoneIcon, ShieldIcon, UsersIcon, VideoIcon } from "./Icons";

// One-on-one meetings between a creator and the manager who looks after them. Designed, not built: in this
// demo one person plays both sides on one device, and real calls need a telephony provider that bills per
// minute. The card says so before it is opened, so nobody clicks into a dead end.

const COPY = {
  creator: {
    title: "Talk it through with your manager",
    lead: "Some things are easier said than typed. Ask for a one-on-one by chat, voice or video.",
  },
  manager: {
    title: "One-on-one requests",
    lead: "Creators will be able to ask you for a meeting. You pick the time and the way: chat, voice or video.",
  },
};

const STEPS = [
  {
    Icon: ChatIcon,
    title: "The creator asks",
    body: "From a piece or a finding: what it is about, the ways that suit them (chat, voice, video, or any) and a few times that work.",
  },
  {
    Icon: CalendarIcon,
    title: "The manager answers",
    body: "Accept as asked, or reply with another way or time. Either side can move it until it is agreed.",
  },
  {
    Icon: UsersIcon,
    title: "They meet",
    body: "Chat stays inside Verytas. Voice and video connect through a temporary link or number that works only for that slot.",
  },
  {
    Icon: CheckIcon,
    title: "It goes on the record",
    body: "The time, the way and a short outcome note are attached to the piece and the audit log. Calls are not recorded.",
  },
];

export function MeetingPreview({ side, className = "" }: { side: "creator" | "manager"; className?: string }) {
  const [open, setOpen] = useState(false);
  const copy = COPY[side];
  return (
    <>
      <section aria-label={copy.title}
        className={`flex flex-col gap-3 rounded-[14px] border border-dashed border-line-strong px-4 py-4 sm:flex-row sm:items-center md:px-5 ${className}`}>
        <div className="flex min-w-0 flex-1 items-start gap-3 sm:items-center">
          <span aria-hidden className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent/12 text-accent"><UsersIcon size={18} /></span>
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-semibold">
              {copy.title}
              <PlannedBadge />
            </p>
            <p className="mt-1 text-[13px] leading-5 text-muted">{copy.lead}</p>
          </div>
        </div>
        <button type="button" onClick={() => setOpen(true)} className="vt-btn vt-btn-quiet h-9 shrink-0 self-start text-xs sm:self-center">
          See how it will work
        </button>
      </section>
      {open && <MeetingDialog onClose={() => setOpen(false)} />}
    </>
  );
}

function PlannedBadge() {
  return (
    <span className="rounded-full border border-line bg-sunken px-2 py-0.5 text-[11px] font-medium text-muted">
      Planned · not in this demo
    </span>
  );
}

function MeetingDialog({ onClose }: { onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useModalFocus(panel, onClose);

  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]"
        onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="vt-pop relative flex max-h-[calc(100dvh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-line bg-raised shadow-[var(--vt-shadow-pop)]">
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold">One-on-one meetings</h2>
            <p className="mt-1"><PlannedBadge /></p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
            <CloseIcon size={16} />
          </button>
        </div>

        <div className="flex min-h-0 flex-col gap-6 overflow-y-auto px-5 py-5">
          <p className="text-sm leading-6 text-muted">
            Escalations settle one finding in writing. Some disagreements need a conversation: a campaign brief, a run
            of pieces sent back, a rule that keeps tripping someone up. A meeting request is the on-the-record way to
            have that conversation, instead of a personal number in a comment (which the escalation screen refuses today).
          </p>

          <ol className="grid gap-4 sm:grid-cols-2">
            {STEPS.map(({ Icon, title, body }, i) => (
              <li key={title} className="flex gap-3">
                <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-sunken text-muted"><Icon size={15} /></span>
                <div className="min-w-0">
                  <p className="text-sm font-medium"><span className="text-subtle">{i + 1}.</span> {title}</p>
                  <p className="mt-0.5 text-[13px] leading-5 text-muted">{body}</p>
                </div>
              </li>
            ))}
          </ol>

          {/* A picture of the request, not a form: nothing here can be pressed. */}
          <figure className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4" aria-label="What a request would look like">
            <figcaption className="text-[11px] font-medium uppercase tracking-wide text-subtle">What a request would look like</figcaption>
            <div className="flex flex-col gap-2.5 text-[13px]">
              <Row label="About">Festive offer reel caption <span className="text-subtle">· 2 must-fix</span></Row>
              <Row label="Ways">
                <span className="flex flex-wrap gap-1.5">
                  <Way Icon={ChatIcon} label="Chat" on />
                  <Way Icon={PhoneIcon} label="Voice" on />
                  <Way Icon={VideoIcon} label="Video" />
                </span>
              </Row>
              <Row label="Times">Thu 4 to 6 pm, or Fri morning</Row>
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-sunken px-3 py-2 text-[13px]">
              <CalendarIcon size={14} className="shrink-0 text-accent" />
              <span className="min-w-0"><strong className="font-semibold">Meera</strong> proposed Fri, 11:00 by voice</span>
            </div>
          </figure>

          <div className="flex gap-3 rounded-xl bg-accent/[0.06] p-4">
            <ShieldIcon size={18} className="mt-0.5 shrink-0 text-accent" />
            <div className="min-w-0 text-[13px] leading-5">
              <p className="font-medium">Nobody&apos;s number is shared</p>
              <p className="mt-0.5 text-muted">
                Calls go through a temporary masked number, the way delivery apps connect a rider and a customer. Each
                side sees only the masked number; it opens a few minutes before the slot and stops working after it.
                Video uses a one-time link that expires the same way.
              </p>
            </div>
          </div>

          <p className="border-t border-line pt-4 text-xs leading-5 text-subtle">
            Why it is not in this demo: both sides here are played by one person on one device, so a meeting would be
            with yourself, and masked calling needs a telephony provider that charges per minute. The flow is designed
            and planned for after the hackathon.
          </p>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-12 shrink-0 text-xs text-subtle">{label}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}

function Way({ Icon, label, on = false }: { Icon: typeof ChatIcon; label: string; on?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
      on ? "border-accent/40 bg-accent/10 text-accent" : "border-line text-subtle"}`}>
      <Icon size={12} />{label}
    </span>
  );
}
