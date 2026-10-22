"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SettingsMenu } from "./SettingsMenu";

const LINKS = [
  { href: "/", label: "Dashboard", short: "Dashboard", hint: "Governance at a glance" },
  { href: "/review", label: "Review", short: "Review", hint: "Check content before it ships" },
  { href: "/guidelines", label: "Guideline health", short: "Guidelines", hint: "Which rules are unclear" },
  { href: "/ask", label: "Ask Verytas", short: "Ask", hint: "Questions answered with live charts" },
];

export function SideNav() {
  const pathname = usePathname();
  return (
    <header className="border-b border-line bg-surface md:sticky md:top-0 md:flex md:h-screen md:w-64 md:shrink-0 md:flex-col md:border-b-0 md:border-r">
      <div className="flex items-center gap-2 px-5 py-4 md:py-6">
        <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-sm font-bold text-accent-ink">
          V
        </span>
        <div className="flex-1">
          <p className="text-base font-semibold leading-tight">Verytas</p>
          <p className="text-xs text-muted">Brand governance</p>
        </div>
        <div className="md:hidden"><SettingsMenu compact /></div>
      </div>
      <nav aria-label="Main" className="overflow-x-auto px-3 pb-3 md:pb-6">
        <ul className="flex gap-1 md:flex-col">
          {LINKS.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={`block whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${
                    active ? "bg-accent/10 font-medium text-accent" : "text-ink hover:bg-bg"
                  }`}
                >
                  {/* Short labels on phones so all four tabs fit on one line. */}
                  <span className="md:hidden">{link.short}</span>
                  <span className="hidden md:inline">{link.label}</span>
                  <span className="hidden text-xs font-normal text-muted md:block">{link.hint}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {/* Settings sit at the bottom of the sidebar on wide screens. */}
      <div className="hidden border-t border-line p-3 md:mt-auto md:block">
        <SettingsMenu />
      </div>
    </header>
  );
}
