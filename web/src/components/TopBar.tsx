"use client";

import { usePathname } from "next/navigation";
import { GlobalSearch } from "./GlobalSearch";

/**
 * A slim bar over the main column that follows the page as it scrolls. It takes no clicks of its own: only
 * the search inside it does, so the page header and whatever sits beside the bar stay reachable.
 */
export function TopBar() {
  const pathname = usePathname();
  // Nobody is signed in on the sign-in pages, so there is nothing to search.
  if (pathname === "/signin" || pathname.startsWith("/signin/")) return null;
  return (
    <div className="vt-topbar pointer-events-none sticky top-0 z-40 flex justify-end px-4 py-2 md:justify-center md:px-10 md:py-3">
      <GlobalSearch />
    </div>
  );
}
