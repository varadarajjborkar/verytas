import type { Metadata } from "next";
import { Suspense } from "react";
import { CreatorsView } from "@/components/creators/CreatorsView";
import { PageHeader, PageSkeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Creators" };

export default function Page() {
  return (
    <>
      <PageHeader title="Creators" lead="Everyone writing for the brand. Open a creator to see how their work tracks against it." refresh />
      {/* The creator being viewed is read from the URL, which needs a Suspense boundary to prerender. */}
      <Suspense fallback={<PageSkeleton />}>
        <CreatorsView />
      </Suspense>
    </>
  );
}
