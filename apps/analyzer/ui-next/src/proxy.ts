import { NextResponse } from "next/server";

// Dev/local pass-through: no Clerk middleware.
export default function proxy() {
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"],
};
