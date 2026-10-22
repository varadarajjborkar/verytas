// Which side of the console this server is. The brand team and creators get
// separate apps (separate ports, later separate hosts) from the same code:
// VERYTAS_APP=manager or VERYTAS_APP=creator fixes the side, its account and
// its screens. Unset, one server shows both, with a "View as" switch while
// sign-in is off: handy on a laptop, never used once the two are deployed.

export type AppSide = "manager" | "creator";

const raw = process.env.VERYTAS_APP;
export const APP: AppSide | null = raw === "manager" || raw === "creator" ? raw : null;

export const APP_NAME: Record<AppSide, string> = { manager: "Brand Console", creator: "Studio" };

/** Each app keeps its own sign-in. Browsers share localhost cookies across ports, and so would the two apps
 * on one host, so signing into one would otherwise sign into both. */
export const SESSION_COOKIE = APP ? `vt_session_${APP}` : "vt_session";

/** Screens each app serves. Anything else redirects home, so a creator app never renders a brand-team page. */
export const ONLY_FOR: Record<string, AppSide> = {
  "/library": "manager",
  "/guidelines": "manager",
  "/escalations": "manager",
};
