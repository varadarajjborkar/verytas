"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { getMe } from "@/lib/review-client";
import { type Side, sideOf } from "@/lib/roles";
import type { Me } from "@/lib/types";

type Viewer = {
  me: Me | null;
  side: Side;
  /** Set when this server is one side's app (lib/app.ts); null when one server shows both. */
  app: Side | null;
  /** Still asking the API who this is; pages hold back side-specific screens until it settles. */
  loading: boolean;
  /** True when sign-in is off and both a brand-team and a creator account are configured. */
  canSwitch: boolean;
  /** No API configured: screens fall back to labelled sample data. */
  demo: boolean;
  switchTo: (side: Side) => Promise<void>;
};

const ViewerContext = createContext<Viewer>({
  me: null, side: "manager", app: null, loading: true, canSwitch: false, demo: false, switchTo: async () => {},
});
export const useViewer = () => useContext(ViewerContext);

export function ViewerProvider({ children, app }: { children: ReactNode; app: Side | null }) {
  const [me, setMe] = useState<Me | null>(null);
  const [persona, setPersona] = useState<{ available: boolean; persona: Side; demo?: boolean } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    Promise.all([
      getMe().catch(() => null),
      fetch("/api/persona").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([who, p]) => {
      if (!live) return;
      setMe(who);
      setPersona(p);
      setLoading(false);
    });
    return () => { live = false; };
  }, []);

  const switchTo = useCallback(async (side: Side) => {
    const res = await fetch("/api/persona", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ persona: side }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.error ?? "Could not switch views.");
    // Every screen, cached list and open review belongs to the account it was loaded as, so a full
    // load (not a client navigation) starts the other side clean.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/");
  }, []);

  // A one-sided app is that side. Otherwise the account's role decides, and the persona cookie only
  // picks which account is used; demo mode has no account and shows the brand team's view.
  const side: Side = app ?? (me ? sideOf(me.role) : (persona?.persona ?? "manager"));
  return (
    <ViewerContext.Provider value={{ me, side, app, loading, canSwitch: !app && Boolean(persona?.available), demo: Boolean(persona?.demo),
      switchTo }}>
      {children}
    </ViewerContext.Provider>
  );
}
