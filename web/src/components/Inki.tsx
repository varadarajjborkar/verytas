// Inki, the workspace assistant: Ask Inki, and "@Inki" in conversations. The mark is a raster with its own
// filled face, so it reads on both themes without a variant.
//
// At rest both eyes are open (public/inki.png). Hovered, or inside a hovered link or button, it winks: the
// artwork's own wink (inki-wink.png) sits underneath, covered by a copy of the open eye (inki-eye.png) that
// shuts and fades to let the wink show, then comes back. The motion lives in globals.css (.vt-inki).

export const INKI = "Inki";

export function InkiIcon({ size = 16, className = "", still = false }: { size?: number; className?: string; still?: boolean }) {
  if (still) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- a 256px static mark; next/image adds nothing here
      <img src="/inki.png" alt="" aria-hidden width={size} height={size} draggable={false}
        className={`shrink-0 select-none object-contain ${className}`} />
    );
  }
  return (
    <span aria-hidden className={`vt-inki relative inline-block shrink-0 select-none ${className}`} style={{ width: size, height: size }}>
      {/* eslint-disable-next-line @next/next/no-img-element -- static marks layered for the wink */}
      <img src="/inki-wink.png" alt="" width={size} height={size} draggable={false} className="block h-full w-full object-contain" />
      <span className="vt-inki-patch" />
      {/* eslint-disable-next-line @next/next/no-img-element -- static marks layered for the wink */}
      <img src="/inki-eye.png" alt="" draggable={false} className="vt-inki-eye" />
    </span>
  );
}
