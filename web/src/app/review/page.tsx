import type { Metadata } from "next";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { PageHeader } from "@/components/ui";
import { demoBody } from "@/lib/demo-data";

export const metadata: Metadata = { title: "Review" };

export default function Page() {
  return (
    <>
      <PageHeader
        title="Review content before it ships"
        lead="Paste a draft. Verytas checks it against your rules, approved facts and confidential terms, explains every issue with its source, and suggests the smallest fix. You decide what changes."
      />
      <ReviewWorkspace initialBody={demoBody} />
    </>
  );
}
