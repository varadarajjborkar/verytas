import type { ReactNode } from "react";
import { FindingDeck } from "./FindingDeck";
import { CheckIcon } from "./Icons";
import { Wordmark } from "./Wordmark";

const PROMISES = [
  "Claims are checked against facts the brand approved",
  "Every flag says why and cites its source",
  "People make the final call, and it is recorded",
];

/**
 * The front door, for the demo picker and the token form alike: what Verytas is on the left (a real
 * finding, the way the product shows one), the way in on the right. Stacks on a phone, brand first but
 * short, so the choice is still on the first screen.
 */
export function SignInShell({ children }: { children: ReactNode }) {
  return (
    <div className="vt-card mx-auto grid w-full max-w-6xl overflow-hidden md:min-h-[calc(100vh-4.5rem)] md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <aside className="vt-signin-aside relative flex flex-col gap-8 border-b border-line p-6 md:border-b-0 md:border-r md:p-10">
        <Wordmark size="lg" />
        <div className="flex flex-col gap-3">
          <h2 className="text-[1.65rem] font-semibold leading-tight tracking-tight md:text-[2rem]">
            Brand review that shows its work.
          </h2>
          <p className="max-w-md text-sm leading-6 text-muted">
            Every post, caption and piece of artwork is checked before it goes out, and every flag comes with
            the rule or fact behind it.
          </p>
        </div>

        <FindingDeck />

        <ul className="hidden flex-col gap-2.5 text-sm sm:flex">
          {PROMISES.map((p) => (
            <li key={p} className="flex items-start gap-2.5">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent/12 text-accent"><CheckIcon size={12} /></span>
              <span className="text-muted">{p}</span>
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex flex-col gap-7 bg-surface p-6 md:p-10">{children}</section>
    </div>
  );
}
