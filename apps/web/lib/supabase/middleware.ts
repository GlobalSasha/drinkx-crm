import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

type CookieToSet = { name: string; value: string; options?: Record<string, unknown> };

export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (toSet: CookieToSet[]) => {
          for (const c of toSet) request.cookies.set(c.name, c.value);
          response = NextResponse.next({ request });
          for (const c of toSet)
            response.cookies.set(c.name, c.value, c.options as Parameters<typeof response.cookies.set>[2]);
        },
      },
    },
  );
  // IMPORTANT: must call getUser to refresh tokens
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return { response, user };
}
