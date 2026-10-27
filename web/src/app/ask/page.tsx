import type { Metadata } from "next";
import { AskInki } from "@/components/AskInki";

export const metadata: Metadata = { title: "Ask Inki" };

export default function Page() {
  return <AskInki />;
}
