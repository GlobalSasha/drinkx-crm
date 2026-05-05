// Sign-in page — taste-soft style.
// Real Supabase Google OAuth wiring happens in Sprint 1.1.3 once SUPABASE_* env vars are set.
// For now this is a static UI placeholder that explains the flow.

import Link from "next/link";

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

      <div className="relative max-w-md w-full bg-white border border-black/10 rounded-2xl p-12 shadow-soft">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted mb-3">
          ВХОД В CRM
        </div>
        <h1 className="text-4xl font-extrabold tracking-[-0.035em] leading-none mb-2">
          drinkx<span className="text-accent">.</span>crm
        </h1>
        <p className="text-muted text-sm mb-8 leading-relaxed">
          Войди через Google — за 2 минуты настроим всё что нужно: профиль,
          рабочие часы, каналы. AI начнёт помогать с первой карточки.
        </p>

        {/* Google sign-in button — wired up in Sprint 1.1.3 */}
        <button
          disabled
          className="w-full py-3.5 px-4 rounded-pill border border-black/10 bg-white flex items-center justify-center gap-3 text-sm font-medium hover:border-accent/30 transition-all duration-700 ease-soft active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <span
            className="w-[18px] h-[18px] rounded-full"
            style={{
              background:
                "conic-gradient(from 0deg, #4285f4 25%, #34a853 25% 50%, #fbbc05 50% 75%, #ea4335 75%)",
            }}
          />
          Войти через Google
          <span className="font-mono text-[10px] tracking-wider text-muted ml-2">
            (нужен Supabase setup)
          </span>
        </button>

        <div className="my-6 flex items-center gap-3 text-[11px] font-mono text-muted">
          <div className="flex-1 h-px bg-black/10" />
          ИЛИ
          <div className="flex-1 h-px bg-black/10" />
        </div>

        <div className="text-xs text-muted mb-2 font-mono uppercase tracking-wider">
          Если у тебя есть invite-ссылка от админа
        </div>
        <input
          type="text"
          disabled
          placeholder="https://crm.drinkx.tech/invite/abc123…"
          className="w-full bg-black/[0.03] border border-black/10 rounded-lg px-4 py-2.5 text-sm text-ink placeholder:text-muted-2 disabled:cursor-not-allowed"
        />

        <p className="text-[11px] text-muted-3 mt-8 leading-relaxed text-center">
          При входе создаётся профиль менеджера в workspace DrinkX.
          <br />
          Используем только email и имя из Google · никакой почтовой переписки
          без явного согласия.
        </p>

        <div className="mt-6 pt-6 border-t border-black/10 text-center">
          <Link href="/" className="text-xs text-muted hover:text-accent">
            ← на главную
          </Link>
        </div>
      </div>
    </main>
  );
}
