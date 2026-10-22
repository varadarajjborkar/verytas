import { connection } from "next/server";
import { Suspense } from "react";
import { DashboardView } from "@/components/DashboardView";
import { PageHeader, SourceBadge } from "@/components/ui";
import { getGuidelineHealth, getOverview, getRecurring } from "@/lib/backend";

async function Dashboard() {
  // Always read at request time, so configuring the backend later takes effect without a rebuild.
  await connection();
  const [overview, recurring, health] = await Promise.all([getOverview(), getRecurring(), getGuidelineHealth()]);
  const source = [overview, recurring, health].every((s) => s.source === "live") ? "live" : "demo";
  return (
    <>
      <PageHeader
        title="Governance dashboard"
        lead="Everything Verytas checked before it reached your audience, which rules do the work, and where the guidelines themselves need attention."
        aside={<SourceBadge source={source} />}
      />
      <DashboardView overview={overview.data} recurring={recurring.data} health={health.data} />
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading governance data…</p>}>
      <Dashboard />
    </Suspense>
  );
}
