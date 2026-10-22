"use client";

import { ThemeProvider } from "@openuidev/react-ui";
import { createContext, type ReactNode, useCallback, useContext, useSyncExternalStore } from "react";
import { useStored, writeStored } from "@/lib/stored";
import { ToastProvider } from "./Toaster";

export type ThemeChoice = "light" | "dark" | "system";
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
      <ThemeProvider mode={mode}>
        <ToastProvider>{children}</ToastProvider>
      </ThemeProvider>
    </ThemeContext.Provider>
  );
}
