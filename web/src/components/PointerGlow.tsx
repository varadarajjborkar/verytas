"use client";

import { useEffect, useRef } from "react";

const STEP = 18; // the dot grid's spacing (globals.css, .vt-signin-aside)
const LIFE = 650;
const REACH = 240;
const BAND = 46;

const isDark = () => {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
};

/**
 * The landing page's pointer glow and click ripple, for a panel that carries the same dot grid. It lives
 * inside its parent and listens only there, so the effect stays on that panel: the glow eases after a
 * mouse or trackpad, and a click sends a ring through the grid's own dots that fades as it spreads. Touch
 * screens get the ripple without the glow; reduced motion keeps the glow without easing and drops the
 * ripple. Same strengths and timing as public/welcome/index.html, so the two read as one site.
 */
export function PointerGlow() {
  const layer = useRef<HTMLDivElement>(null);
  const glow = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const box = layer.current?.parentElement;
    const g = glow.current, cv = canvas.current, ctx = cv?.getContext("2d");
    if (!box || !g || !cv || !ctx || !layer.current) return;
    const area = layer.current;
    const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let x = 0, y = 0, tx = 0, ty = 0, easing = 0, drawing = 0;
    let rings: { x: number; y: number; t: number }[] = [];

    const size = () => {
      const r = area.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
      cv.width = r.width * dpr;
      cv.height = r.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const place = () => {
      const half = g.offsetWidth / 2;
      g.style.transform = `translate3d(${x - half}px,${y - half}px,0)`;
    };
    const ease = () => {
      x += (tx - x) * 0.12;
      y += (ty - y) * 0.12;
      place();
      easing = Math.abs(tx - x) + Math.abs(ty - y) > 0.5 ? requestAnimationFrame(ease) : 0;
    };
    const draw = (now: number) => {
      const r = area.getBoundingClientRect(), b = box.getBoundingClientRect();
      ctx.clearRect(0, 0, r.width, r.height);
      rings = rings.filter((ring) => now - ring.t < LIFE);
      const rgb = isDark() ? "120, 175, 255" : "26, 95, 209";
      // The grid is the panel's background, anchored to its box; this layer scrolls with its content.
      const ox = (((b.left - r.left + 1) % STEP) + STEP) % STEP, oy = (((b.top - r.top + 1) % STEP) + STEP) % STEP;
      for (const ring of rings) {
        const k = (now - ring.t) / LIFE, radius = REACH * (1 - (1 - k) ** 3), fade = 1 - k;
        const x0 = Math.floor((ring.x - radius - BAND - ox) / STEP) * STEP + ox;
        const y0 = Math.floor((ring.y - radius - BAND - oy) / STEP) * STEP + oy;
        for (let gx = x0; gx <= ring.x + radius + BAND; gx += STEP) {
          for (let gy = y0; gy <= ring.y + radius + BAND; gy += STEP) {
            const off = Math.abs(Math.hypot(gx - ring.x, gy - ring.y) - radius);
            if (off > BAND) continue;
            const a = fade * (1 - off / BAND);
            ctx.fillStyle = `rgba(${rgb},${(0.85 * a).toFixed(3)})`;
            ctx.beginPath();
            ctx.arc(gx, gy, 1 + 0.9 * a, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
      drawing = rings.length ? requestAnimationFrame(draw) : 0;
    };
    const at = (e: PointerEvent) => {
      const r = area.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top] as const;
    };

    const move = (e: PointerEvent) => {
      if (!fine || (e.pointerType !== "mouse" && e.pointerType !== "pen")) return;
      [tx, ty] = at(e);
      g.dataset.on = "";
      if (still) { x = tx; y = ty; place(); } else if (!easing) easing = requestAnimationFrame(ease);
    };
    const leave = () => { delete g.dataset.on; };
    const down = (e: PointerEvent) => {
      if (still || e.button !== 0) return;
      const [px, py] = at(e);
      rings.push({ x: px, y: py, t: performance.now() });
      if (!drawing) drawing = requestAnimationFrame(draw);
    };

    const watch = new ResizeObserver(size);
    watch.observe(area);
    box.addEventListener("pointermove", move, { passive: true });
    box.addEventListener("pointerleave", leave);
    box.addEventListener("pointerdown", down, { passive: true });
    return () => {
      watch.disconnect();
      box.removeEventListener("pointermove", move);
      box.removeEventListener("pointerleave", leave);
      box.removeEventListener("pointerdown", down);
      cancelAnimationFrame(easing);
      cancelAnimationFrame(drawing);
    };
  }, []);

  return (
    <div ref={layer} aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div ref={glow} className="vt-pointer-glow" />
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
    </div>
  );
}
