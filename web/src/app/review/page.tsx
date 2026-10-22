import type { Metadata } from "next";
import { Suspense } from "react";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { PageHeader, PageSkeleton } from "@/components/ui";
import { APP } from "@/lib/app";
import { demoBody } from "@/lib/demo-data";

export const metadata: Metadata = { title: "Review" };

export default function Page() {
  return (
    <>
      {APP === "manager"
        ? <PageHeader title="Review queue" lead="Every creator's pieces, ranked by what needs you first." />
        : <PageHeader title={APP === "creator" ? "My reviews" : "Review"} />}
      {/* The open review is read from the URL, which needs a Suspense boundary to prerender. */}
      <Suspense fallback={<PageSkeleton />}>
        <ReviewWorkspace initialBody={demoBody} />
      </Suspense>
    </>
  );
}
