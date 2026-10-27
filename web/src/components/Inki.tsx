// Inki, the workspace assistant: Ask Inki, and "@Inki" in conversations. The mark is a raster with its own
// filled face, so it reads on both themes without a variant; it takes the icon props so the nav can use it.

export const INKI = "Inki";

export function InkiIcon({ size = 16, className = "" }: { size?: number; className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- a 256px static mark; next/image adds nothing here
    <img src="/inki.png" alt="" aria-hidden width={size} height={size} draggable={false}
      className={`shrink-0 select-none object-contain ${className}`} />
  );
}
