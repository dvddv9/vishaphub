"use client";

import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { API_URL } from "@/lib/api";
import { IS_DESKTOP } from "@/lib/desktop";

type State = "checking" | "ready" | "waking";

const PING_EVERY_MS = 5000;
const PING_TIMEOUT_MS = 4000;
/** After this long the free-tier wake-up is no longer the likely explanation. */
const GIVE_UP_AFTER_S = 90;

/**
 * Free hosting puts the backend to sleep; the first request can take 30-50 s.
 * Ping /health every 5 s until it answers, so the visitor sees "waking up" instead
 * of an app that looks broken. Stops pinging once the server is ready.
 */
export default function ServerStatus() {
  const [state, setState] = useState<State>("checking");
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (IS_DESKTOP) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();

    async function ping() {
      const controller = new AbortController();
      const abort = setTimeout(() => controller.abort(), PING_TIMEOUT_MS);
      try {
        const response = await fetch(`${API_URL}/health`, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (response.ok) {
          if (!cancelled) setState("ready");
          return;
        }
      } catch {
        /* asleep or unreachable: try again below */
      } finally {
        clearTimeout(abort);
      }
      if (cancelled) return;
      setState("waking");
      timer = setTimeout(ping, PING_EVERY_MS);
    }

    void ping();
    const tick = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      clearInterval(tick);
    };
  }, []);

  if (IS_DESKTOP || state === "checking") return null;

  if (state === "ready") {
    return (
      <p
        role="status"
        className="inline-flex items-center gap-2 text-xs text-slate-600"
      >
        <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
        Server ready
      </p>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
    >
      <LoaderCircle className="mt-0.5 h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
      <span>
        {elapsed < GIVE_UP_AFTER_S ? (
          <>
            Waking the server up. Free hosting sleeps when idle, so the first request can take up
            to 50 seconds. <span className="font-mono">Elapsed: {elapsed}s</span>
          </>
        ) : (
          <>
            The server has not answered for {elapsed} seconds. Try again in a minute; if it stays
            down, the service may be under maintenance.
          </>
        )}
      </span>
    </div>
  );
}
