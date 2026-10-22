import type { Metadata } from "next";
import { Suspense } from "react";
import { LibraryView } from "@/components/library/LibraryView";
import { PageHeader, PageSkeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Brand library" };

export default function Page() {
  return (
    <>
      <PageHeader title="Brand library" lead="The rules, facts, confidential terms and artwork every review checks against." />
      {/* The open tab is read from the URL, which needs a Suspense boundary to prerender. */}
      <Suspense fallback={<PageSkeleton />}>
        <LibraryView />
      </Suspense>
    </>
  );
}
