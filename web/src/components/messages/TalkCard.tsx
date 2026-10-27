import Link from "next/link";
import { ChatIcon } from "../Icons";
import { INKI } from "../Inki";

// Where the home screens point people at a conversation. A finding is settled by an escalation; this is for
// what needs talking through (a brief, a run of pieces sent back, a rule that keeps tripping someone up).

const COPY = {
  creator: {
    title: "Talk it through with the brand team",
    lead: `Message the person reviewing your work about a piece, ask @${INKI} where it stands, or share a Meet or Teams link to talk.`,
  },
  manager: {
    title: "Talk it through with a creator",
    lead: `Some things are quicker said than written in a finding. Message the creator, bring in @${INKI}, or share a call link.`,
  },
};

export function TalkCard({ side, className = "" }: { side: "creator" | "manager"; className?: string }) {
  const copy = COPY[side];
  return (
    <section aria-label={copy.title}
      className={`flex flex-col gap-3 rounded-[14px] border border-line bg-raised px-4 py-4 sm:flex-row sm:items-center md:px-5 ${className}`}>
      <div className="flex min-w-0 flex-1 items-start gap-3 sm:items-center">
        <span aria-hidden className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent/12 text-accent"><ChatIcon size={18} /></span>
        <div className="min-w-0">
          <p className="text-sm font-semibold">{copy.title}</p>
          <p className="mt-1 text-[13px] leading-5 text-muted">{copy.lead}</p>
        </div>
      </div>
      <Link href="/messages" className="vt-btn vt-btn-quiet shrink-0 self-start sm:self-center">Open messages</Link>
    </section>
  );
}
