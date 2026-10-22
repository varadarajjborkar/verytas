"use client";

import { ThemeProvider } from "@openuidev/react-ui";
import { createContext, type ReactNode, useCallback, useContext, useSyncExternalStore } from "react";
import { useStored, writeStored } from "@/lib/stored";
import { ToastProvider } from "./Toaster";

export type ThemeChoice = "light" | "dark" | "system";

// OpenUI's charts, tables and cards read our own tokens, so generated answers
// follow the app's palette and its light and dark modes with no second theme.
// Chart palettes stay literal: charts paint SVG attributes, where CSS variables
// don't resolve.
const CHART = ["#3d8bf2", "#22b8a6", "#e0a04a", "#e0604f", "#7cc4f0", "#8a93a3"];
const OPENUI_THEME = {
  background: "var(--vt-bg)",
  foreground: "var(--vt-surface)",
  popoverBackground: "var(--vt-raised)",
  sunkLight: "var(--vt-surface)",
  sunk: "var(--vt-sunken)",
  sunkDeep: "var(--vt-sunken)",
  elevatedLight: "var(--vt-raised)",
  elevated: "var(--vt-raised)",
  elevatedStrong: "var(--vt-raised)",
  elevatedIntense: "var(--vt-raised)",
  textNeutralPrimary: "var(--vt-ink)",
  textNeutralSecondary: "var(--vt-muted)",
  textNeutralTertiary: "var(--vt-subtle)",
  textNeutralLink: "var(--vt-accent)",
  textBrand: "var(--vt-accent)",
  textAccentPrimary: "var(--vt-accent-ink)",
  interactiveAccentDefault: "var(--vt-accent)",
  interactiveAccentHover: "var(--vt-accent)",
  interactiveAccentPressed: "var(--vt-accent)",
  borderDefault: "var(--vt-line)",
  borderInteractive: "var(--vt-line-strong)",
  borderAccent: "var(--vt-accent)",
  chatUserResponseBg: "var(--vt-sunken)",
  chatUserResponseText: "var(--vt-ink)",
  fontBody: "var(--font-geist-sans), system-ui, sans-serif",
  defaultChartPalette: CHART,
  barChartPalette: CHART,
  lineChartPalette: CHART,
  areaChartPalette: CHART,
  pieChartPalette: CHART,
  radarChartPalette: CHART,
  radialChartPalette: CHART,
  horizontalBarChartPalette: CHART,
};
const KEY = "vt-theme";

const ThemeContext = createContext<{ choice: ThemeChoice; setChoice: (c: ThemeChoice) => void }>({
  choice: "system",
  setChoice: () => {},
});
export const useTheme = () => useContext(ThemeContext);

// The system preference as an external store, so components re-render when the OS theme flips.
const darkQuery = () => window.matchMedia("(prefers-color-scheme: dark)");
const subscribeSystem = (cb: () => void) => {
  const q = darkQuery();
  q.addEventListener("change", cb);
  return () => q.removeEventListener("change", cb);
};

export function Providers({ children }: { children: ReactNode }) {
  const stored = useStored(KEY);
  const choice: ThemeChoice = stored === "light" || stored === "dark" ? stored : "system";
  const systemDark = useSyncExternalStore(subscribeSystem, () => darkQuery().matches, () => false);

  const setChoice = useCallback((c: ThemeChoice) => {
    // If storage is blocked the attribute still applies for this visit.
    writeStored(KEY, c === "system" ? null : c);
    if (c === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = c;
  }, []);

  const mode = choice === "system" ? (systemDark ? "dark" : "light") : choice;
  return (
    <ThemeContext.Provider value={{ choice, setChoice }}>
      <ThemeProvider mode={mode} lightTheme={OPENUI_THEME} darkTheme={OPENUI_THEME}>
        <ToastProvider>{children}</ToastProvider>
      </ThemeProvider>
    </ThemeContext.Provider>
  );
}
