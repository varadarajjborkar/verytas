import type { Metadata } from "next";
import { Suspense } from "react";
import { ConversationsView } from "@/components/conversations/ConversationsView";
import { PageSkeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Conversations" };

export default function Page() {
  return (
    // The open conversation is read from the URL, which needs a Suspense boundary to prerender.
    <Suspense fallback={<PageSkeleton />}>
      <ConversationsView />
    </Suspense>
  );
}
