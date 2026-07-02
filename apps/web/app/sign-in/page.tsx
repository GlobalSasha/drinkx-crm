"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { T } from "@/lib/design-system";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

function SignInForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextParam = searchParams.get("next") ?? "/today";
  const errorParam = searchParams.get("error");

  const [email, setEmail] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(
    errorParam === "auth_callback_failed" ? "Ошибка авторизации. Попробуй ещё раз." : null,
  );

  // Redirect already-signed-in users
  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    supabase.auth.getUser().then(({ data }) => {
      if (data.user) router.replace("/today");
    });
  }, [router]);

  async function handleGoogle() {
    setLoading(true);
    setError(null);
    const supabase = getSupabaseBrowserClient();
    const origin = window.location.origin;
    const { error: oauthError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${origin}/auth/callback?next=${encodeURIComponent(nextParam)}`,
      },
    });
    if (oauthError) {
      setError(
        oauthError.message.includes("provider is not enabled")
          ? "Google OAuth не включён в Supabase Dashboard. Используй magic link ниже."
          : oauthError.message,
      );
      setLoading(false);
    }
    // on success the browser is redirected by Supabase — no further action needed
  }

  async function handleTestUser() {
    setLoading(true);
    setError(null);
    const supabase = getSupabaseBrowserClient();
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: "test@drinkx.tech",
      password: "DrinkX_Test_2026!",
    });
    if (signInError) {
      setError(signInError.message);
      setLoading(false);
      return;
    }
    router.replace(nextParam as never);
  }

  async function handleMagicLink(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    setError(null);
    const supabase = getSupabaseBrowserClient();
    const origin = window.location.origin;
    const { error: otpError } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${origin}/auth/callback?next=${encodeURIComponent(nextParam)}`,
      },
    });
    if (otpError) {
      setError(otpError.message);
    } else {
      setOtpSent(true);
    }
    setLoading(false);
  }

  return (
    <div className="relative max-w-md w-full bg-white border border-brand-border rounded-card p-6 sm:p-12">
      <div className={`${T.mono} text-brand-muted mb-3`}>
        ВХОД В CRM
      </div>
      <h1 className="type-page-title tracking-[-0.035em] leading-none mb-2">
        drinkx<span className="text-brand-accent">.</span>crm
      </h1>
      <p className="text-brand-muted text-sm mb-8 leading-relaxed">
        Войди через Google — за 2 минуты настроим всё что нужно: профиль,
        рабочие часы, каналы. AI начнёт помогать с первой карточки.
      </p>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-rose/10 border border-rose/20 text-sm text-rose">
          {error}
        </div>
      )}

      {/* Google sign-in button */}
      <button
        onClick={handleGoogle}
        disabled={loading}
        className="w-full py-3.5 px-4 rounded-full border border-brand-border bg-white flex items-center justify-center gap-3 text-sm font-medium hover:border-brand-accent/30 transition duration-700 ease-soft active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
      >
        <span
          className="w-[18px] h-[18px] rounded-full shrink-0"
          style={{
            background:
              "conic-gradient(from 0deg, #4285f4 25%, #34a853 25% 50%, #fbbc05 50% 75%, #ea4335 75%)",
          }}
        />
        Войти через Google
      </button>

      <div className={`my-6 flex items-center gap-3 ${T.mono} text-brand-muted`}>
        <div className="flex-1 h-px bg-black/10" />
        ИЛИ
        <div className="flex-1 h-px bg-black/10" />
      </div>

      {otpSent ? (
        <div className="text-center py-4">
          <p className="text-sm font-semibold text-brand-primary mb-1">Проверь почту</p>
          <p className="text-xs text-brand-muted">
            Мы отправили magic link на{" "}
            <span className="font-mono text-brand-accent">{email}</span>.
            Перейди по ссылке в письме чтобы войти.
          </p>
          <button
            onClick={() => {
              setOtpSent(false);
              setEmail("");
            }}
            className="mt-4 text-xs text-brand-muted hover:text-brand-accent underline"
          >
            Отправить снова
          </button>
        </div>
      ) : (
        <form onSubmit={handleMagicLink} className="space-y-3">
          <div className="type-caption text-brand-muted">
            Magic link на email
          </div>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@drinkx.tech"
            required
            className="w-full bg-black/[0.03] border border-brand-border rounded-lg px-4 py-2.5 text-sm text-brand-primary placeholder:text-brand-muted focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1/40"
          />
          <button
            type="submit"
            disabled={loading || !email}
            className="w-full py-3 px-4 rounded-full bg-brand-accent text-white text-sm font-medium hover:bg-brand-accent/90 transition active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? "Отправляем…" : "Получить ссылку"}
          </button>
        </form>
      )}

      <div className={`my-6 flex items-center gap-3 ${T.mono} text-brand-muted`}>
        <div className="flex-1 h-px bg-black/10" />
        ИЛИ
        <div className="flex-1 h-px bg-black/10" />
      </div>

      <button
        onClick={handleTestUser}
        disabled={loading}
        className="w-full py-2.5 px-4 rounded-full border border-brand-border bg-transparent text-sm text-brand-muted hover:text-brand-primary hover:border-brand-border transition duration-300 active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
      >
        🧪 Войти как тестовый пользователь
      </button>

      <p className="text-xs text-brand-muted mt-8 leading-relaxed text-center">
        При входе создаётся профиль менеджера в workspace DrinkX.
        <br />
        Используем только email и имя из Google · никакой почтовой переписки
        без явного согласия.
      </p>

      <div className="mt-6 pt-6 border-t border-brand-border text-center">
        <Link href="/" className="text-xs text-brand-muted hover:text-brand-accent">
          ← на главную
        </Link>
      </div>
    </div>
  );
}

export default function SignInPage() {
  return (
    <main className="min-h-screen flex items-center justify-center p-6 relative overflow-hidden">
      {/* Ambient mesh */}
      <div className="absolute inset-0 pointer-events-none">
        <div
          className="absolute -top-40 -left-40 w-[700px] h-[700px] rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle at 30% 30%, #5A8C7A, transparent 60%)" }}
        />
        <div
          className="absolute top-40 -right-40 w-[560px] h-[560px] rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle at 60% 60%, #D8B98E, transparent 60%)" }}
        />
      </div>
      <Suspense fallback={null}>
        <SignInForm />
      </Suspense>
    </main>
  );
}
