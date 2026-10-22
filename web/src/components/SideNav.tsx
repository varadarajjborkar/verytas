"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { usePersistedFlag } from "@/lib/persisted-flag";
import { DashboardIcon, GaugeIcon, PanelIcon, ReviewIcon, SparkIcon } from "./Icons";
import { SettingsMenu } from "./SettingsMenu";

const LINKS = [
  { href: "/", label: "Dashboard", Icon: DashboardIcon },
  { href: "/review", label: "Review", Icon: ReviewIcon },
  { href: "/guidelines", label: "Guideline health", short: "Guidelines", Icon: GaugeIcon },
  { href: "/ask", label: "Ask Verytas", short: "Ask", Icon: SparkIcon },
];

export function SideNav() {
  const pathname = usePathname();
  // Desktop only: on phones the nav is already a single row of tabs.
  const [collapsed, setCollapsed] = usePersistedFlag("vt-nav-collapsed", false);
  const toggle = (
    <button type="button" onClick={() => setCollapsed(!collapsed)} aria-expanded={!collapsed} aria-controls="main-nav"
      aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      className="hidden h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink md:grid">
      <PanelIcon size={17} />
    </button>
  );

  return (
    <header className={`border-b border-line bg-surface/70 backdrop-blur md:sticky md:top-0 md:flex md:h-screen md:shrink-0 md:flex-col md:border-b-0 md:border-r md:transition-[width] md:duration-300 md:ease-out ${
      collapsed ? "md:w-[4.5rem]" : "md:w-60"}`}>
      <div className={`flex items-center gap-2.5 px-5 py-4 md:py-6 ${collapsed ? "md:flex-col md:px-0" : ""}`}>
        <span aria-hidden className="vt-mark grid h-8 w-8 shrink-0 place-items-center rounded-[10px] text-sm font-bold">V</span>
        <p className={`flex-1 text-[15px] font-semibold tracking-tight ${collapsed ? "md:sr-only" : ""}`}>Verytas</p>
        {toggle}
        <div className="md:hidden"><SettingsMenu compact /></div>
      </div>
      <nav id="main-nav" aria-label="Main" className={`overflow-x-auto pb-3 md:pb-6 ${collapsed ? "px-3 md:px-2.5" : "px-3"}`}>
        <ul className="flex gap-1 md:flex-col">
          {LINKS.map(({ href, label, short, Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <li key={href}>
                <Link href={href} aria-current={active ? "page" : undefined} title={collapsed ? label : undefined}
                  className={`flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${
                    collapsed ? "md:justify-center md:px-0 md:py-2.5" : ""} ${
                    active ? "bg-accent/12 font-medium text-accent" : "text-muted hover:bg-sunken hover:text-ink"}`}>
                  <Icon size={17} className="shrink-0" />
                  {/* Short labels on phones so all four tabs fit on one line. */}
                  <span className="md:hidden">{short ?? label}</span>
                  <span className={`hidden md:inline ${collapsed ? "md:sr-only" : ""}`}>{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className={`hidden md:mt-auto md:block ${collapsed ? "px-2.5 py-3 [&>button]:mx-auto" : "p-3"}`}>
        <SettingsMenu compact={collapsed} />
      </div>
    </header>
  );
}
