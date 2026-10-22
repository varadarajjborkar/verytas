import type { Metadata } from "next";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { PageHeader } from "@/components/ui";
import { demoBody } from "@/lib/demo-data";

export const metadata: Metadata = { title: "Review" };

export default function Page() {
  return (
    <>
      <PageHeader title="Review" lead="Check a draft against your rules and facts before it ships." />
      <ReviewWorkspace initialBody={demoBody} />
    </>
  );
}
