"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { DashboardIcon, GaugeIcon, ReviewIcon, SparkIcon } from "./Icons";
import { SettingsMenu } from "./SettingsMenu";

const LINKS = [
  { href: "/", label: "Dashboard", Icon: DashboardIcon },
  { href: "/review", label: "Review", Icon: ReviewIcon },
  { href: "/guidelines", label: "Guideline health", short: "Guidelines", Icon: GaugeIcon },
  { href: "/ask", label: "Ask Verytas", short: "Ask", Icon: SparkIcon },
];

export function SideNav() {
  const pathname = usePathname();
  return (
    <header className="border-b border-line bg-surface/70 backdrop-blur md:sticky md:top-0 md:flex md:h-screen md:w-60 md:shrink-0 md:flex-col md:border-b-0 md:border-r">
      <div className="flex items-center gap-2.5 px-5 py-4 md:py-6">
        <span aria-hidden className="vt-mark grid h-8 w-8 place-items-center rounded-[10px] text-sm font-bold">V</span>
        <p className="flex-1 text-[15px] font-semibold tracking-tight">Verytas</p>
        <div className="md:hidden"><SettingsMenu compact /></div>
      </div>
      <nav aria-label="Main" className="overflow-x-auto px-3 pb-3 md:pb-6">
        <ul className="flex gap-1 md:flex-col">
          {LINKS.map(({ href, label, short, Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <li key={href}>
                <Link href={href} aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${
                    active ? "bg-accent/12 font-medium text-accent" : "text-muted hover:bg-sunken hover:text-ink"}`}>
                  <Icon size={17} className="shrink-0" />
                  {/* Short labels on phones so all four tabs fit on one line. */}
                  <span className="md:hidden">{short ?? label}</span>
                  <span className="hidden md:inline">{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="hidden p-3 md:mt-auto md:block">
        <SettingsMenu />
      </div>
    </header>
  );
}
