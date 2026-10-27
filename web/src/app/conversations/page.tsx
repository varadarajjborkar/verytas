import type { Metadata } from "next";
import { Suspense } from "react";
import { MessagesView } from "@/components/messages/MessagesView";
import { PageSkeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Messages" };

export default function Page() {
  return (
    // The open conversation is read from the URL, which needs a Suspense boundary to prerender.
    <Suspense fallback={<PageSkeleton />}>
      <MessagesView />
    </Suspense>
  );
}
