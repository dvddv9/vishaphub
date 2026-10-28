"use client";

import { useEffect, useState } from "react";

/**
 * Elapsed-time line for a running analysis. The backend reports only
 * queued / running / done, not the current stage, so this shows real time and an
 * honest expectation instead of a made-up stage indicator.
 */
export default function RunProgress({ since }: { since?: string | null }) {
  // Only rendered after the visitor submits, never during the server render, so reading the clock
  // in the initial state cannot cause a hydration mismatch.
  const [mountedAt] = useState(() => Date.now());
  const [now, setNow] = useState(mountedAt);

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, []);

  const parsed = since ? Date.parse(since) : NaN;
  const origin = Number.isFinite(parsed) ? Math.min(parsed, mountedAt) : mountedAt;
  const seconds = Math.max(0, Math.floor((now - origin) / 1000));

  return (
    <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-700">
      <p>
        <span className="font-mono">Elapsed: {seconds}s</span>
        {seconds > 60 ? (
          <span className="text-slate-600"> · still working, large inputs take longer</span>
        ) : null}
      </p>
      <p className="mt-1 text-xs text-slate-600">
        A full run usually takes 30 to 90 seconds. The server works through orchestrator, scanner,
        analyst, researcher (only when needed), synthesizer and transmitter. This page opens the
        report on its own when it is ready.
      </p>
    </div>
  );
}
