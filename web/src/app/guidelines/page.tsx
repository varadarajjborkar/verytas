import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";
import { GuidelineHealthView } from "@/components/GuidelineHealthView";
import { PageHeader, SourceBadge } from "@/components/ui";
import { getGuidelineHealth } from "@/lib/backend";

export const metadata: Metadata = { title: "Guideline health" };

async function Health() {
  // Always read at request time, so configuring the backend later takes effect without a rebuild.
  await connection();
  const health = await getGuidelineHealth();
  return (
    <>
      <PageHeader
        title="Guideline health"
        lead="Most tools only judge the content. Verytas also judges the rulebook: when reviewers keep overriding a rule, disagree with each other about it, or say it is unclear, the rule is the problem."
        aside={<SourceBadge source={health.source} />}
      />
      <GuidelineHealthView health={health.data} />
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading guideline health…</p>}>
      <Health />
    </Suspense>
  );
}
