/**
 * Build the Next.js bundle for the Tauri desktop shell.
 *
 * `next build` must see `NEXT_PUBLIC_DESKTOP=1` *in its own environment*: Next
 * inlines `NEXT_PUBLIC_*` values into the client bundle, and `next.config.ts`
 * reads the same flag to switch on `output: 'export'`. npm scripts cannot set an
 * environment variable portably (cmd.exe vs sh), so this wrapper does it.
 *
 * Invoked by `npm run build:desktop`, which is what `src-tauri/tauri.conf.json`
 * runs as `beforeBuildCommand`.
 */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, "..");

console.log("==> next build with NEXT_PUBLIC_DESKTOP=1 (static export)");

/**
 * The desktop bundle talks to the loopback IPv4 API, never to `localhost`:
 * `localhost` can resolve to `::1`, while uvicorn binds `0.0.0.0` (IPv4 only) —
 * the request then fails with "Cannot reach the Vishap API".
 *
 * Set here rather than only in `.env.local` so a developer's local `.env` cannot
 * silently regress the packaged app to `localhost`.
 */
const DESKTOP_API_URL = "http://127.0.0.1:5001";

const result = spawnSync("next", ["build"], {
  cwd: projectRoot,
  // stdio: "inherit" keeps the log readable and avoids buffering the build.
  stdio: "inherit",
  shell: true,
  env: {
    ...process.env,
    NEXT_PUBLIC_DESKTOP: "1",
    NEXT_PUBLIC_API_URL: DESKTOP_API_URL,
  },
});

if (result.error) {
  console.error(`Failed to start next build: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
