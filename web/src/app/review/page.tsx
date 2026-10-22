import type { Metadata } from "next";
import { Suspense } from "react";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { PageHeader, PageSkeleton } from "@/components/ui";
import { demoBody } from "@/lib/demo-data";

export const metadata: Metadata = { title: "Review" };

export default function Page() {
  return (
    <>
      <PageHeader title="Review" />
      {/* The open review is read from the URL, which needs a Suspense boundary to prerender. */}
      <Suspense fallback={<PageSkeleton />}>
        <ReviewWorkspace initialBody={demoBody} />
      </Suspense>
    </>
  );
}
