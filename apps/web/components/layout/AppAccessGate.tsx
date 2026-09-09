"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api-client";
import { useMe } from "@/lib/hooks/use-me";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

function isInviteRequired(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 403) return false;
  if (!error.body || typeof error.body !== "object") return false;

  const detail = (error.body as { detail?: unknown }).detail;
  return (
    !!detail &&
    typeof detail === "object" &&
    "code" in detail &&
    (detail as { code?: unknown }).code === "invite_required"
  );
}

// Plan 026: a persistent 401 means the backend rejected the session (JWT
// expired/rotated while middleware still sees a cookie). Route back to
// sign-in instead of stranding the user on the retry card.
function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export function AppAccessGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const me = useMe();
  const denied = isInviteRequired(me.error);
  const unauthorized = isUnauthorized(me.error);

  useEffect(() => {
    if (!denied && !unauthorized) return;

    const supabase = getSupabaseBrowserClient();
    const dest = denied
      ? "/sign-in?error=invite_required"
      : "/sign-in";
    void supabase.auth.signOut().finally(() => {
      router.replace(dest);
    });
  }, [denied, unauthorized, router]);

  if (me.isPending || denied || unauthorized) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-brand-bg">
        <div className="flex items-center gap-3 text-sm text-brand-muted">
          <Loader2 size={20} className="animate-spin" />
          Проверяем доступ…
        </div>
      </main>
    );
  }

  if (me.isError) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-brand-bg p-6">
        <div className="max-w-sm text-center">
          <h1 className="type-card-title text-brand-primary">
            Не удалось проверить доступ
          </h1>
          <p className="text-sm text-brand-muted mt-2">
            Проверьте соединение и попробуйте ещё раз.
          </p>
          <button
            type="button"
            onClick={() => void me.refetch()}
            className="mt-4 px-5 py-2.5 rounded-full bg-brand-accent text-white text-sm font-semibold"
          >
            Повторить
          </button>
        </div>
      </main>
    );
  }

  return children;
}
