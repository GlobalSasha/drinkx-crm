import { type NextRequest, NextResponse } from "next/server";
import { DEV_STUB_USER, devAuthBypassEnabled } from "@/lib/dev-auth";
import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  // Локальный стенд без Supabase (ADR-014 на стороне фронтенда): ни одного
  // сетевого вызова в Auth, личность — та же, под которой бэкенд принимает
  // запросы в stub-режиме. Включается только флагом и только вне
  // production-сборки, см. lib/dev-auth.ts.
  const { response, user } = devAuthBypassEnabled()
    ? { response: NextResponse.next({ request }), user: DEV_STUB_USER }
    : await updateSession(request);
  const pathname = request.nextUrl.pathname;

  // Public routes
  const isPublic =
    pathname.startsWith("/sign-in") ||
    pathname.startsWith("/auth/callback") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api/") ||
    /\.[a-z0-9]+$/i.test(pathname); // static files

  // The root is an entry point, not a page
  if (pathname === "/") {
    const url = request.nextUrl.clone();
    url.pathname = user ? "/today" : "/sign-in";
    url.search = "";
    return NextResponse.redirect(url);
  }

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  // Already signed in users hitting /sign-in → bounce to /today
  if (user && pathname.startsWith("/sign-in")) {
    const url = request.nextUrl.clone();
    url.pathname = "/today";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
