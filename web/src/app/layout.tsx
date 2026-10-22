import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "@openuidev/react-ui/styles/index.css";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { SideNav } from "@/components/SideNav";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const THEME_BOOT = `try{var t=localStorage.getItem("vt-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export const metadata: Metadata = {
  title: { default: "Verytas", template: "%s · Verytas" },
  description: "Pre-publication brand governance: cited checks, human review, guidelines that learn.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        {/* Apply a saved theme before first paint, so dark mode never flashes white. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body className="min-h-full">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Providers>
          <div className="flex min-h-screen w-full flex-col overflow-x-clip md:flex-row">
            <SideNav />
            <main id="main" className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
