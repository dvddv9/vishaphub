import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Navbar from "@/components/Navbar";
import { IS_DESKTOP } from "@/lib/desktop";
import pkg from "../../package.json";
import { DEFAULT_THEME, THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

/** Single source of truth: ui-next/package.json (kept equal to pyproject.toml by scripts/check_version.py). */
const VISHAP_VERSION: string = pkg.version;
const GITHUB_URL = "https://github.com/dvddv9/vishap";

export const metadata: Metadata = {
  title: "Vishap — Security analysis for engineering materials",
  description:
    "6-stage LLM pipeline with SAST/SCA, STRIDE threat model, audit trail, SARIF 2.1.0 and SCA reporting.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const page = (
    <html
      lang="en"
      data-theme={DEFAULT_THEME}
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* applies a stored "light" choice before the first paint (dark is the default) */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">
        <Navbar />
        <main className="w-full flex-1">{children}</main>
        <footer className="border-t border-slate-200 bg-white">
          <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-2 px-4 py-6 text-sm text-slate-600 sm:flex-row">
            <p>
              Vishap <span className="font-mono">v{VISHAP_VERSION}</span> — security analysis for
              engineering materials.
            </p>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="transition-colors hover:text-slate-900"
            >
              GitHub
            </a>
          </div>
        </footer>
      </body>
    </html>
  );

  // The desktop build has no auth server: ClerkProvider needs a publishable key
  // and its CDN, and every Clerk hook throws without the provider. A
  // single-user local tool does not need one, so the shell is served bare.
  if (IS_DESKTOP || !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY.includes("ZXhhbXBsZ")) return page;

  return page;
}


