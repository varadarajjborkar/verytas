/**
 * Brings an element into view inside its own scrolling column, and only there. scrollIntoView also scrolls
 * every ancestor, the window included, so picking an issue in one column used to drag the whole page along
 * with it. This moves the nearest scroller just far enough, and never past the element's top: a tall,
 * freshly opened row shows its head first instead of being scrolled to its end.
 *
 * The window is left alone unless `page` is set; a single-column phone layout opts in where moving the page
 * is the point (a highlight tapped in the text opening its row in the list below).
 */
export function reveal(el: Element | null | undefined, { page = false, top = 12, bottom = 12 } = {}) {
  if (!el) return;
  const box = scroller(el);
  if (!box && !page) return;
  const area = box ? box.getBoundingClientRect() : { top: 0, bottom: window.innerHeight };
  const r = el.getBoundingClientRect();
  const above = r.top - (area.top + top);
  const below = r.bottom - (area.bottom - bottom);
  // Already whole in view: nothing moves.
  const by = above < 0 ? above : below > 0 ? Math.min(below, above) : 0;
  if (Math.abs(by) < 1) return;
  const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  (box ?? window).scrollBy({ top: by, behavior: smooth ? "smooth" : "auto" });
}

function scroller(el: Element): HTMLElement | null {
  for (let n = el.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
    const { overflowY } = getComputedStyle(n);
    if ((overflowY === "auto" || overflowY === "scroll") && n.scrollHeight > n.clientHeight) return n;
  }
  return null;
}
