import { connection } from "next/server";
import { Suspense } from "react";
import { DashboardView } from "@/components/DashboardView";
import { CreatorHome } from "@/components/home/CreatorHome";
import { ManagerHome } from "@/components/home/ManagerHome";
import { PageHeader, PageSkeleton, SourceBadge } from "@/components/ui";
import { getGuidelineHealth, getOverview, getRecurring, getViewer } from "@/lib/backend";
import { sideOf } from "@/lib/roles";

async function Home() {
  // Always read at request time, so configuring the backend later takes effect without a rebuild.
  await connection();
  const viewer = await getViewer();
  if (viewer && sideOf(viewer.role) === "creator") {
    return (
      <>
        <PageHeader title="My work" lead="Your pieces, what each one needs next, and what the brand team said." />
        <CreatorHome />
      </>
    );
  }
  const [overview, recurring, health] = await Promise.all([getOverview(), getRecurring(), getGuidelineHealth()]);
  const source = [overview, recurring, health].every((s) => s.source === "live") ? "live" : "demo";
  return (
    <>
      <PageHeader title="Dashboard" lead="What needs a decision, how work is flowing, and what Verytas caught."
        aside={<SourceBadge source={source} />} />
      <ManagerHome overview={overview.data} health={health.data} />
      <h2 className="mb-3 mt-9 text-sm font-semibold text-muted">Brand health</h2>
      <DashboardView overview={overview.data} recurring={recurring.data} health={health.data} />
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Home />
    </Suspense>
  );
}
