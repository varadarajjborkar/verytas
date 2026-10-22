import type { Metadata } from "next";
import { PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "How Verytas uses AI" };

const SERVICES: [string, string, string][] = [
  ["Ollama Cloud: gpt-oss", "Finds claims, judges tone and messaging, writes explanations and fixes, weighs disputes, answers Ask Verytas",
    "Only redacted text. Confidential terms are replaced before anything leaves."],
  ["Ollama Cloud: gemma", "Reads images and video frames, compares artwork with the brand's official assets",
    "Never for confidential pieces. Images are blacked out where confidential text appears."],
  ["On this server", "Reads text in images (OCR), transcribes video speech, matches artwork, renders PDFs, checks wording, contacts and links",
    "Nothing leaves the machine."],
  ["Optional: TypeSafe Jev or Anthropic Claude", "An alternative judge or writer, if the brand team switches it on",
    "Same redaction as above."],
];

/** The AI disclosure the brief asks for, in plain words, reachable from every screen of both apps. */
export default function Page() {
  return (
    <div className="max-w-3xl">
      <PageHeader title="How Verytas uses AI" lead="AI helps review content before it is published. People make every decision." />
      <div className="flex flex-col gap-8 text-sm leading-6">
        <section aria-labelledby="ai-does">
          <h2 id="ai-does" className="text-base font-semibold">What AI does</h2>
          <ul className="mt-2 list-disc pl-5 text-muted marker:text-subtle">
            <li>Finds possible issues in text, images, documents and video, each tied to the rule or approved fact it cites.</li>
            <li>Explains why something was flagged and how sure it is.</li>
            <li>Suggests a fix that keeps what the writer meant. Nothing changes until a person applies it.</li>
            <li>Answers questions about pieces and review data in Ask Verytas.</li>
          </ul>
        </section>
        <section aria-labelledby="people-do">
          <h2 id="people-do" className="text-base font-semibold">What people decide</h2>
          <ul className="mt-2 list-disc pl-5 text-muted marker:text-subtle">
            <li>Approving, sending back and publishing are always a person&apos;s call. AI never approves or publishes.</li>
            <li>Any finding can be disputed, dismissed with a reason, or escalated to the brand team.</li>
            <li>A must-fix finding can only be set aside by an approver, who picks a reason (a note is optional), and the call is recorded.</li>
          </ul>
        </section>
        <section aria-labelledby="ai-services">
          <h2 id="ai-services" className="text-base font-semibold">Models and services</h2>
          <div className="mt-3 overflow-x-auto rounded-xl border border-line">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="bg-sunken text-xs text-muted">
                <tr><th scope="col" className="px-4 py-2 font-medium">Service</th><th scope="col" className="px-4 py-2 font-medium">Used for</th>
                  <th scope="col" className="px-4 py-2 font-medium">What it sees</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {SERVICES.map(([name, use, sees]) => (
                  <tr key={name} className="align-top">
                    <th scope="row" className="px-4 py-2.5 font-medium">{name}</th>
                    <td className="px-4 py-2.5 text-muted">{use}</td>
                    <td className="px-4 py-2.5 text-muted">{sees}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-subtle">
            Without an AI service configured, model-judged checks fall back to simple rules and the review marks them as limited.
            Every review lists the exact models that saw it, under &ldquo;How it was checked&rdquo;.
          </p>
        </section>
        <section aria-labelledby="ai-limits">
          <h2 id="ai-limits" className="text-base font-semibold">Limits</h2>
          <p className="mt-2 text-muted">
            AI can be wrong, and some checks read some languages better than others; the review says which checks could
            read a piece. Treat findings as a careful second reader, not a verdict, and tell the brand team when one is off:
            those decisions teach Verytas where its rules are unclear.
          </p>
        </section>
      </div>
    </div>
  );
}
