import { NextResponse, type NextRequest } from "next/server";
import { getSupabaseServerClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const next = url.searchParams.get("next") ?? "/today";

  // Behind nginx the Next.js process binds to 0.0.0.0:3000, so request.url
  // resolves to https://0.0.0.0:3000 — useless for client-facing redirects.
  // Build the redirect base from the forwarded headers nginx sends.
  const host =
    request.headers.get("x-forwarded-host") ??
    request.headers.get("host") ??
    url.host;
  const proto =
    request.headers.get("x-forwarded-proto") ?? url.protocol.replace(/:$/, "");
  const baseUrl = `${proto}://${host}`;

  if (code) {
    const supabase = await getSupabaseServerClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(new URL(next, baseUrl));
    }
  }

  // Fallback: send back to /sign-in with error flag
  const fallback = new URL("/sign-in", baseUrl);
  fallback.searchParams.set("error", "auth_callback_failed");
  return NextResponse.redirect(fallback);
}
