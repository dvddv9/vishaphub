"use client";

import { useSyncExternalStore } from "react";

/**
 * Subscribe to a CSS media query. The server render (and the first client render)
 * answers `false`, so markup matches during hydration; the real answer arrives right after.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Phones: below Tailwind's `sm` breakpoint (640px). */
export function useIsNarrow(): boolean {
  return useMediaQuery("(max-width: 639px)");
}
