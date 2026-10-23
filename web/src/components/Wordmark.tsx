import { Logo } from "./Logo";

// The mark and the name together, sized as one: the name's cap height sits near the middle third of the
// mark, in the heavy display face (layout.tsx) so the word carries the same weight as the drawing.
const SIZES = {
  sm: { mark: 32, text: "text-[21px]" },
  lg: { mark: 44, text: "text-[29px]" },
} as const;

/** The name's type, for places that lay the mark and name out themselves (the collapsible sidebar). */
export const NAME = "font-display font-extrabold leading-none tracking-[-0.03em]";

export function Wordmark({ size = "sm", className = "" }: { size?: keyof typeof SIZES; className?: string }) {
  const s = SIZES[size];
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <Logo size={s.mark} className="shrink-0" />
      <span className={`${NAME} ${s.text}`}>Verytas</span>
    </span>
  );
}
