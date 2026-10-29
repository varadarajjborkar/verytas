import { connection } from "next/server";
import { Suspense } from "react";
import { CustomizeButton, ManagerDashboard } from "@/components/dashboard/ManagerDashboard";
import { CreatorHome } from "@/components/home/CreatorHome";
import { GettingStarted } from "@/components/home/GettingStarted";
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
        <PageHeader title="My work" lead="Your pieces, what each one needs next, and what the brand team said." refresh />
        <GettingStarted />
        <CreatorHome />
      </>
    );
  }
  const [overview, recurring, health] = await Promise.all([getOverview(), getRecurring(), getGuidelineHealth()]);
  const source = [overview, recurring, health].every((s) => s.source === "live") ? "live" : "demo";
  return (
    <>
      <PageHeader title="Dashboard" lead="What needs a decision, how work is flowing, and what Verytas caught." refresh
        aside={<div className="flex items-center gap-2"><SourceBadge source={source} /><CustomizeButton /></div>} />
      <GettingStarted />
      <ManagerDashboard overview={overview.data} recurring={recurring.data} health={health.data} />
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
