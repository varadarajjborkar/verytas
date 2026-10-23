"use client";

import { useState } from "react";
import type { AssistKind } from "@/lib/assist";
import { SparkIcon } from "../Icons";
import { useViewer } from "../Viewer";
import { AssistPanel } from "./AssistPanel";

// The roles the API lets open a dossier (reviewer, approver, brand admin). Checked again there; this only
// decides whether the button is worth showing. Creators and auditors never see it.
const ROLES = new Set(["reviewer", "approver", "brand_admin"]);

/** "Summarize" for the brand team on a piece or an escalation. Renders nothing for anyone else. */
export function SummarizeButton({ kind, id, title, className = "vt-btn vt-btn-quiet" }: {
  kind: AssistKind; id: number; title: string; className?: string;
}) {
  const { me } = useViewer();
  const [open, setOpen] = useState(false);
  if (!me || !ROLES.has(me.role)) return null;
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={className} aria-haspopup="dialog"
        title="A short brief of this item, and a chat about it">
        <SparkIcon size={14} className="text-accent" />Summarize
      </button>
      {open && <AssistPanel kind={kind} id={id} title={title} onClose={() => setOpen(false)} />}
    </>
  );
}
