"use client";

/**
 * Desktop stand-in for `@clerk/nextjs`.
 *
 * `next.config.ts` aliases the Clerk package to this module when
 * `NEXT_PUBLIC_DESKTOP=1`. Rendering gates alone are not enough: a static
 * `import` of Clerk pulls its barrel into every route, and that barrel registers
 * two server actions (`invalidateCacheAction`, `deleteKeylessAction`) — which a
 * static export refuses to build ("Server Actions are not supported with static
 * export"). Swapping the package keeps Clerk out of the desktop bundle entirely.
 *
 * The desktop app is single-user and the backend listens on 127.0.0.1, so there
 * is nothing to sign in to.
 */
import type { ReactNode } from "react";

export function ClerkProvider({ children }: { children?: ReactNode }) {
  return <>{children}</>;
}

export function SignInButton(_props: Record<string, unknown>) {
  return null;
}

export function UserButton(_props: Record<string, unknown>) {
  return null;
}

/** Same shape as Clerk's hook, permanently signed out. */
export function useUser() {
  return { isLoaded: true, isSignedIn: false as const, user: null };
}

export function useAuth() {
  return { isLoaded: true, isSignedIn: false as const, userId: null };
}
