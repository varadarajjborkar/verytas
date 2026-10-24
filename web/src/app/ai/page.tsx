import type { Metadata } from "next";
import { AiInfoContent } from "@/components/AiInfo";
import { PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "How Verytas uses AI" };

/** The AI disclosure for direct links; in the app it opens over the page from "How AI is used". */
export default function Page() {
  return (
    <div className="max-w-3xl">
      <PageHeader title="How Verytas uses AI" lead="AI reads and suggests. People decide." />
      <AiInfoContent />
    </div>
  );
}
