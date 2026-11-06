"use client";
import { createBrowserClient } from "@supabase/ssr";

import { devAuthBypassEnabled } from "@/lib/dev-auth";

// Локальный вход без Supabase: сессии нет, и клиент никуда не ходит, но без
// адреса и ключа он падает при создании и роняет всю оболочку приложения.
const DEV_BYPASS_URL = "http://localhost:54321";
const DEV_BYPASS_KEY = "dev-auth-bypass";

export function getSupabaseBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (devAuthBypassEnabled()) {
    return createBrowserClient(url || DEV_BYPASS_URL, key || DEV_BYPASS_KEY);
  }
  return createBrowserClient(url!, key!);
}
