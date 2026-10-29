import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";
import { GuidelineHealthView } from "@/components/GuidelineHealthView";
import { PostPerformance } from "@/components/PostPerformance";
import { ForBrandTeam } from "@/components/library/LibraryView";
import { PageHeader, PageSkeleton, SourceBadge } from "@/components/ui";
import { getGuidelineHealth, getViewer } from "@/lib/backend";
import { sideOf } from "@/lib/roles";

export const metadata: Metadata = { title: "Guideline health" };

async function Health() {
  // Always read at request time, so configuring the backend later takes effect without a rebuild.
  await connection();
  const viewer = await getViewer();
  if (viewer && sideOf(viewer.role) === "creator") {
    return <><PageHeader title="Guideline health" /><ForBrandTeam /></>;
  }
  const health = await getGuidelineHealth();
  return (
    <>
      <PageHeader title="Guideline health" lead="Rules reviewers keep overriding are the ones to rewrite." refresh
        aside={<SourceBadge source={health.source} />} />
      <GuidelineHealthView health={health.data} />
      {health.source === "live" && <PostPerformance canImport={viewer?.role !== "auditor"} />}
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Health />
    </Suspense>
  );
}
