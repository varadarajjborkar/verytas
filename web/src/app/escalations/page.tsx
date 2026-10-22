import type { Metadata } from "next";
import { Suspense } from "react";
import { EscalationsInbox } from "@/components/escalations/EscalationsInbox";
import { PageHeader, PageSkeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Escalations" };

export default function Page() {
  return (
    <>
      <PageHeader title="Escalations" lead="Creators asked a person to look. Decide with the passage, the record and their words side by side." />
      {/* The tab and the focused request are read from the URL, which needs a Suspense boundary to prerender. */}
      <Suspense fallback={<PageSkeleton />}>
        <EscalationsInbox />
      </Suspense>
    </>
  );
}
