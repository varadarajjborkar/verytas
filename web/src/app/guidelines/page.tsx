import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";
import { GuidelineHealthView } from "@/components/GuidelineHealthView";
import { PageHeader, PageSkeleton, SourceBadge } from "@/components/ui";
import { getGuidelineHealth } from "@/lib/backend";

export const metadata: Metadata = { title: "Guideline health" };

async function Health() {
  // Always read at request time, so configuring the backend later takes effect without a rebuild.
  await connection();
  const health = await getGuidelineHealth();
  return (
    <>
      <PageHeader title="Guideline health" lead="Rules reviewers keep overriding are the ones to rewrite."
        aside={<SourceBadge source={health.source} />} />
      <GuidelineHealthView health={health.data} />
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
