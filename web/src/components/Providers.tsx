"use client";

import { ThemeProvider } from "@openuidev/react-ui";
import type { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  return <ThemeProvider mode="light">{children}</ThemeProvider>;
}
