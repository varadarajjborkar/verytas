"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { usePersistedFlag } from "@/lib/persisted-flag";
import { ROLE_LABEL } from "@/lib/roles";
import { useEffect, useState } from "react";
import { countEscalations } from "@/lib/review-client";
import { BookIcon, DashboardIcon, GaugeIcon, HomeIcon, InboxIcon, PanelIcon, ReviewIcon, SparkIcon, UsersIcon } from "./Icons";
import { Logo } from "./Logo";
import { NAME } from "./Wordmark";
import { SettingsMenu } from "./SettingsMenu";
import { useViewer } from "./Viewer";
import { AiInfoButton } from "./AiInfo";

type NavLink = { href: string; label: string; short?: string; Icon: typeof HomeIcon };
const REVIEW: NavLink = { href: "/review", label: "Review", Icon: ReviewIcon };
const ASK: NavLink = { href: "/ask", label: "Ask Verytas", short: "Ask", Icon: SparkIcon };
// Each side sees only its own screens. Until the viewer is known, only the shared ones show,
// so a creator never glimpses the brand team's links.
const LINKS: Record<"creator" | "manager" | "loading", NavLink[]> = {
  creator: [{ href: "/", label: "My work", short: "Home", Icon: HomeIcon },
    { href: "/review", label: "My reviews", short: "Reviews", Icon: ReviewIcon }, ASK],
  manager: [
    { href: "/", label: "Dashboard", Icon: DashboardIcon },
    { href: "/review", label: "Review queue", short: "Queue", Icon: ReviewIcon },
    { href: "/escalations", label: "Escalations", short: "Asks", Icon: InboxIcon },
    { href: "/creators", label: "Creators", Icon: UsersIcon },
    { href: "/library", label: "Brand library", short: "Library", Icon: BookIcon },
    { href: "/guidelines", label: "Guideline health", short: "Health", Icon: GaugeIcon },
    ASK,
  ],
  loading: [REVIEW, ASK],
};

export function SideNav() {
  const pathname = usePathname();
  const { me, side, app, loading } = useViewer();
  // A one-sided app knows its links before anyone is loaded; a shared server waits for the account.
  const links = LINKS[loading && !app ? "loading" : side];
  const waiting = useOpenEscalations(side === "manager" && !(loading && !app));
  // Desktop only: on phones the nav is already a single row of tabs.
  const [collapsed, setCollapsed] = usePersistedFlag("vt-nav-collapsed", false);
  const demo = useDemoSignin();
  const toggle = (
    <button type="button" onClick={() => setCollapsed(!collapsed)} aria-expanded={!collapsed} aria-controls="main-nav"
      aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      className="hidden h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink md:grid">
      <PanelIcon size={17} />
    </button>
  );

  // The sign-in page comes before any account: there is nothing to navigate yet.
  if (pathname === "/signin" || pathname.startsWith("/signin/")) return null;
  return (
    <header className={`border-b border-line bg-surface/70 backdrop-blur md:sticky md:top-0 md:flex md:h-screen md:shrink-0 md:flex-col md:border-b-0 md:border-r md:transition-[width] md:duration-300 md:ease-out ${
      collapsed ? "md:w-[4.5rem]" : "md:w-60"}`}>
      <div className={`flex items-center gap-2.5 px-5 py-4 md:py-6 ${collapsed ? "md:flex-col md:px-0" : ""}`}>
        {/* The mark and name lead home from any screen. Already home, a click does nothing: navigating to
            the same page would only fetch and render it again. */}
        <Link href="/" aria-current={pathname === "/" ? "page" : undefined} className={`flex flex-1 items-center gap-2.5 rounded-lg ${collapsed ? "md:hidden" : ""}`}
          onClick={(e) => { if (pathname === "/") e.preventDefault(); }}>
          <Logo size={32} className="shrink-0" />
          <p className={`leading-tight ${collapsed ? "md:sr-only" : ""}`}>
            <span className={`block text-[21px] ${NAME}`}>Verytas</span>
            {app && <span className="mt-1 block text-[11px] font-medium text-subtle">{app === "manager" ? "Brand Console" : "Studio"}</span>}
          </p>
        </Link>
        {collapsed ? (
          // Folded, the mark is the way back out: it turns into the expand button under the pointer and back to
          // the mark when the pointer leaves, so the top of the rail holds one thing, not two.
          <button type="button" onClick={() => setCollapsed(false)} aria-expanded={false} aria-controls="main-nav"
            aria-label="Expand sidebar" title="Expand sidebar"
            className="group relative hidden h-10 w-10 place-items-center rounded-lg transition hover:bg-sunken focus-visible:bg-sunken md:grid">
            <Logo size={32} className="transition-[opacity,transform] duration-150 group-hover:scale-90 group-hover:opacity-0 group-focus-visible:opacity-0" />
            <PanelIcon size={18} className="absolute text-ink opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100" />
          </button>
        ) : toggle}
        <div className="md:hidden"><SettingsMenu compact /></div>
      </div>
      <nav id="main-nav" aria-label="Main" className={`overflow-x-auto overflow-y-hidden pb-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [mask-image:linear-gradient(to_right,black_85%,transparent)] md:pb-6 md:[mask-image:none] ${collapsed ? "px-3 md:px-2.5" : "px-3"}`}>
        <ul className="flex gap-1 md:flex-col">
          {links.map(({ href, label, short, Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <li key={href}>
                <Link href={href} aria-current={active ? "page" : undefined} title={collapsed ? label : undefined}
                  className={`relative flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${
                    collapsed ? "md:justify-center md:px-0 md:py-2.5" : ""} ${
                    active ? "bg-accent/12 font-medium text-accent" : "text-muted hover:bg-sunken hover:text-ink"}`}>
                  <Icon size={17} className="shrink-0" />
                  {/* Short labels on phones so the tabs fit on one line. */}
                  <span className="md:hidden">{short ?? label}</span>
                  <span className={`hidden md:inline ${collapsed ? "md:sr-only" : ""}`}>{label}</span>
                  {href === "/escalations" && waiting > 0 && (
                    <span aria-label={`${waiting} waiting`} className={`ml-auto rounded-full bg-accent px-1.5 text-[11px] font-semibold tabular-nums text-accent-ink ${
                      collapsed ? "md:absolute md:right-1.5 md:top-1 md:ml-0 md:px-1 md:text-[10px]" : ""}`}>{waiting}</span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {me && !collapsed && (
        <div className="hidden px-5 pb-1 md:mt-auto md:block">
          <p className="truncate text-xs font-medium">{me.name}</p>
          <p className="truncate text-[11px] text-subtle">
            {side === "creator" ? "Creator" : `Brand team · ${ROLE_LABEL[me.role] ?? me.role}`}
          </p>
          {demo && (
            <button type="button" onClick={switchAccount}
              className="mt-2 block text-xs font-medium text-accent underline-offset-2 hover:underline">
              Switch account
            </button>
          )}
          <AiInfoButton className="mt-2 inline-block text-left text-[11px] text-subtle underline-offset-2 hover:text-ink hover:underline">
            AI-assisted · how AI is used
          </AiInfoButton>
        </div>
      )}
      <div className={`hidden md:block ${me && !collapsed ? "" : "md:mt-auto"} ${collapsed ? "px-2.5 py-3 [&>button]:mx-auto" : "p-3"}`}>
        <SettingsMenu compact={collapsed} />
      </div>
    </header>
  );
}

/** Whether sign-in is the shared demo's account picker. */
function useDemoSignin(): boolean {
  const [demo, setDemo] = useState(false);
  useEffect(() => {
    fetch("/api/session").then((r) => r.json()).then((j) => setDemo(Boolean(j.demo))).catch(() => {});
  }, []);
  return demo;
}

/** Back to the demo's picker: the session ends, the work done as this person stays. */
export async function switchAccount() {
  await fetch("/api/session", { method: "DELETE" }).catch(() => null);
  window.location.assign("/signin");
}

/** Open escalations for the nav badge: checked on load, when the tab regains focus, and each minute. */
function useOpenEscalations(enabled: boolean): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    const check = () => {
      if (document.hidden) return;
      countEscalations().then((r) => { if (live) setCount(r.open); }).catch(() => {});
    };
    check();
    const t = setInterval(check, 60_000);
    window.addEventListener("focus", check);
    return () => { live = false; clearInterval(t); window.removeEventListener("focus", check); };
  }, [enabled]);
  return enabled ? count : 0;
}
