import path from "node:path";
import type { NextConfig } from "next";

/**
 * Desktop (Tauri) builds are static exports loaded from `ui-next/out`.
 *
 * The flag is the environment variable `NEXT_PUBLIC_DESKTOP=1` — the same value
 * the client bundle reads (`src/lib/desktop.ts`). It has to be gated here too:
 * the hosted web app keeps Clerk middleware, and middleware cannot run in a
 * static export.
 */
const isDesktop = process.env.NEXT_PUBLIC_DESKTOP === "1";

/**
 * Clerk is replaced by local stubs in the desktop build.
 *
 * Rendering Clerk only behind `if (IS_DESKTOP)` is not enough: the static import
 * is still analysed, and Clerk's barrel registers two server actions, which a
 * static export refuses to build. Aliasing the package keeps it out of the
 * module graph — and out of the binary.
 */
// `process.cwd()` is the `ui-next` directory: npm runs scripts there, and
// `tauri.conf.json` invokes this through `npm --prefix ../ui-next run ...`.
const clerkDesktop = path.join(process.cwd(), "src", "lib", "clerk-desktop.tsx");
const clerkServerDesktop = path.join(process.cwd(), "src", "lib", "clerk-server-desktop.ts");

// Turbopack resolves alias values as request strings, so it needs paths relative
// to the project root — absolute Windows paths are rejected ("windows imports
// are not implemented yet"). Webpack wants absolute ones.
const clerkDesktopRequest = "./src/lib/clerk-desktop.tsx";
const clerkServerDesktopRequest = "./src/lib/clerk-server-desktop.ts";

const nextConfig: NextConfig = {
  /* config options here */
  // Cache Components turns on Partial Prerendering, which streams at request
  // time — impossible in a static export ("PPR cannot be enabled in export
  // mode"). The desktop build ships a pre-rendered site, so both are off there.
  // No page uses `use cache` / `cacheLife` / `cacheTag`, so nothing is lost.
  cacheComponents: !isDesktop,
  partialPrefetching: !isDesktop,
  // Only the desktop build is exported to plain HTML/CSS/JS (no Node server).
  output: isDesktop ? "export" : undefined,
  // The Next.js image optimizer needs a server; a packaged app cannot call it.
  images: isDesktop ? { unoptimized: true } : undefined,
  turbopack: {
    ...(isDesktop
      ? {
          resolveAlias: {
            "@clerk/nextjs": clerkDesktopRequest,
            "@clerk/nextjs/server": clerkServerDesktopRequest,
          },
        }
      : {}),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Same swap for the webpack bundler (`next build --webpack`).
  webpack: isDesktop
    ? (config) => {
        config.resolve = config.resolve ?? {};
        config.resolve.alias = {
          ...config.resolve.alias,
          "@clerk/nextjs$": clerkDesktop,
          "@clerk/nextjs/server$": clerkServerDesktop,
        };
        return config;
      }
    : undefined,
};

export default nextConfig;
