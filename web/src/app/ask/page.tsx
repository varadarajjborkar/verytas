import type { Metadata } from "next";
import { AskVerytas } from "@/components/AskVerytas";

export const metadata: Metadata = { title: "Ask Verytas" };

export default function Page() {
  return <AskVerytas />;
}
