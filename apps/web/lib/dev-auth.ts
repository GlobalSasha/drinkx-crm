/**
 * Локальный dev-режим входа — зеркало ADR-014 на фронтенде.
 *
 * Бэкенд без `SUPABASE_URL`/`SUPABASE_JWT_SECRET` и вне production принимает
 * запросы под фиксированной личностью `dev@drinkx.tech`. Фронтенд так не умел:
 * `middleware.ts` звал `supabase.auth.getUser()` на каждый запрос, и без
 * реального проекта Supabase ни один защищённый экран локально не открывался
 * вовсе (UX-ENV/README.md — проверено, а не предположение).
 *
 * Включается только явным флагом и только вне production-сборки. Оба условия
 * обязательны: `NODE_ENV` Next подставляет литералом, поэтому в
 * production-бандле `"production" !== "production"` схлопывается в `false`,
 * и обхода там нет не «по договорённости», а физически.
 */

/** Личность из stub-режима бэкенда (`app/auth/jwt.py`). */
export const DEV_STUB_USER = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "dev@drinkx.tech",
} as const;

/**
 * Чистое правило — то же, что применяется в рантайме, но с явными
 * аргументами: его можно проверить тестом, не пересобирая приложение.
 */
export function isDevAuthBypass(
  flag: string | undefined,
  nodeEnv: string | undefined,
): boolean {
  return nodeEnv !== "production" && flag === "1";
}

/**
 * Включён ли обход здесь и сейчас. Читает `process.env` напрямую и только
 * литералами — иначе Next нечего подставить при сборке.
 */
export function devAuthBypassEnabled(): boolean {
  return isDevAuthBypass(
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS,
    process.env.NODE_ENV,
  );
}
