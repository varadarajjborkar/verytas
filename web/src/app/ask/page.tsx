import type { Metadata } from "next";
import { Copilot } from "@/components/Copilot";

export const metadata: Metadata = { title: "Ask Verytas" };

export default function Page() {
  return (
    <div className="flex h-[calc(100vh-4rem)] min-h-[560px] flex-col gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ask Verytas</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Ask about your governance data in plain words. Answers are generated as live charts and tables
          from the same insights the dashboard uses, and never from outside data.
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-line bg-surface">
        <Copilot />
      </div>
    </div>
  );
}
