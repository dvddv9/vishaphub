/**
 * Build-time flag: is this bundle for the Tauri desktop shell?
 *
 * The desktop app is single-user and talks to a backend on `127.0.0.1`, so it
 * runs without Clerk. Set `NEXT_PUBLIC_DESKTOP=1` when building it (see
 * `scripts/build-desktop.mjs`); the hosted web app leaves it unset.
 *
 * `NEXT_PUBLIC_*` values are inlined into the client bundle by Next, so this is
 * a compile-time constant — never a runtime toggle.
 */
export const IS_DESKTOP = process.env.NEXT_PUBLIC_DESKTOP === "1";
