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
 * finding, the way the product shows one), the way in on the right. It takes the whole screen and is laid
 * out to fit one desktop screen; each side still scrolls on its own when a window is too short, so nothing
 * is ever cut off. Stacks on a phone, brand first but short, so the choice is still on the first screen.
 */
export function SignInShell({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 grid overflow-y-auto bg-surface md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:overflow-hidden">
      <aside className="vt-signin-aside relative flex flex-col md:min-h-0 gap-7 p-6 md:overflow-y-auto md:px-12 md:py-10 [@media(min-width:768px)_and_(max-height:760px)]:gap-5 [@media(min-width:768px)_and_(max-height:760px)]:py-8">
        {/* The two halves meet in a fade, not a rule: one surface with the brand side lit at its corner. */}
        <span aria-hidden className="pointer-events-none absolute inset-y-0 right-0 hidden w-32 bg-gradient-to-r from-transparent to-surface md:block" />
        <span aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-b from-transparent to-surface md:hidden" />
        <Wordmark size="lg" />
        <div className="relative flex flex-col gap-3">
          <h2 className="text-[1.65rem] font-semibold leading-tight tracking-tight md:text-[2rem]">
            Brand review that shows its work.
          </h2>
          <p className="max-w-md text-sm leading-6 text-muted">
            Every post, caption and piece of artwork is checked before it goes out, and every flag comes with
            the rule or fact behind it.
          </p>
        </div>

        <div className="relative my-auto"><FindingDeck /></div>

        <ul className="relative hidden flex-col gap-2.5 text-sm sm:flex [@media(min-width:768px)_and_(max-height:760px)]:hidden">
          {PROMISES.map((p) => (
            <li key={p} className="flex items-start gap-2.5">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent/12 text-accent"><CheckIcon size={12} /></span>
              <span className="text-muted">{p}</span>
            </li>
          ))}
        </ul>
      </aside>
      {/* Safe centring: the choice sits mid-screen, and a window too short for it scrolls from the top. */}
      <section className="flex flex-col gap-5 bg-surface [justify-content:safe_center] md:min-h-0 p-6 md:overflow-y-auto md:px-12 md:py-10 [@media(min-width:768px)_and_(max-height:760px)]:gap-4 [@media(min-width:768px)_and_(max-height:760px)]:py-7">
        {children}
      </section>
    </div>
  );
}
