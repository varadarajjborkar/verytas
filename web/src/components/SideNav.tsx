"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard", hint: "Governance at a glance" },
  { href: "/review", label: "Review", hint: "Check content before it ships" },
  { href: "/guidelines", label: "Guideline health", hint: "Which rules are unclear" },
  { href: "/ask", label: "Ask Verytas", hint: "Questions answered with live charts" },
];

export function SideNav() {
  const pathname = usePathname();
  return (
    <header className="border-b border-line bg-surface md:w-64 md:shrink-0 md:border-b-0 md:border-r">
      <div className="flex items-center gap-2 px-5 py-4 md:py-6">
        <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-sm font-bold text-white">
          V
        </span>
        <div>
          <p className="text-base font-semibold leading-tight">Verytas</p>
          <p className="text-xs text-muted">Brand governance</p>
        </div>
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
                  {link.label}
                  <span className="hidden text-xs font-normal text-muted md:block">{link.hint}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
