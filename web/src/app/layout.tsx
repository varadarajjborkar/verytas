import type { Metadata } from "next";
import { Bricolage_Grotesque, Geist, Geist_Mono } from "next/font/google";
import "@openuidev/react-ui/styles/index.css";
import "./globals.css";
import { CookieNotice } from "@/components/CookieNotice";
import { Providers } from "@/components/Providers";
import { SideNav } from "@/components/SideNav";
import { TopBar } from "@/components/TopBar";
import { Tour } from "@/components/Tour";
import { APP, APP_NAME } from "@/lib/app";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
// The name beside the mark (components/Wordmark.tsx): heavy and a little quirky, like the mark itself.
// Only that word uses it; the interface stays in Geist.
const display = Bricolage_Grotesque({ variable: "--font-bricolage", subsets: ["latin"], weight: "800" });

// Also claims OpenUI's development inspector flag before the library loads: its floating button sat on
// top of page content in dev and widened phone layouts. Production builds never include it.
const THEME_BOOT = `try{var t=localStorage.getItem("vt-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`
  + `globalThis[Symbol.for("openui.devtools.autoMount")]=true;`;

const PRODUCT = APP ? `Verytas ${APP_NAME[APP]}` : "Verytas";

export const metadata: Metadata = {
  title: { default: PRODUCT, template: `%s · ${PRODUCT}` },
  description: "Pre-publication brand governance: cited checks, human review, guidelines that learn.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${display.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        {/* Apply a saved theme before first paint, so dark mode never flashes white. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body className="min-h-full">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Providers app={APP}>
          <div className="flex min-h-screen w-full flex-col overflow-x-clip md:flex-row">
            <SideNav />
            <div className="flex min-w-0 flex-1 flex-col">
              <TopBar />
              <main id="main" className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-9">
                <div className="mx-auto w-full max-w-[1320px]">{children}</div>
              </main>
            </div>
          </div>
          <Tour />
          <CookieNotice />
        </Providers>
      </body>
    </html>
  );
}
