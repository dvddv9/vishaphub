/**
 * Desktop stand-in for `@clerk/nextjs/server`, used by `src/proxy.ts`.
 *
 * Aliased in by `next.config.ts` when `NEXT_PUBLIC_DESKTOP=1`: a static export
 * has no server to run middleware, and no session to protect.
 */
import { NextResponse } from "next/server";

export function clerkMiddleware(_handler?: unknown) {
  return () => NextResponse.next();
}

export function createRouteMatcher(_routes: string[]) {
  return () => false;
}
