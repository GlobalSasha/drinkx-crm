// Typed wrapper around fetch for the FastAPI backend.
// Adds JWT from Supabase session and unwraps JSON.

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API ${status}`);
  }
}

async function request<T>(
  method: Method,
  path: string,
  options: { body?: unknown; token?: string; signal?: AbortSignal } = {},
): Promise<T> {
  let token = options.token;
  if (!token && typeof window !== "undefined") {
    const supabase = getSupabaseBrowserClient();
    const { data } = await supabase.auth.getSession();
    token = data.session?.access_token ?? undefined;
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: options.body != null ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      // Non-JSON body — typically an nginx error page (502/504) or a
      // proxy timeout. Surface the raw text inside ApiError instead of
      // letting SyntaxError reach React Query.
      data = { detail: text.slice(0, 500) };
    }
  }

  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export const api = {
  get: <T>(path: string, opts?: { token?: string; signal?: AbortSignal }) =>
    request<T>("GET", path, opts),
  post: <T>(path: string, body?: unknown, opts?: { token?: string }) =>
    request<T>("POST", path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: { token?: string }) =>
    request<T>("PATCH", path, { ...opts, body }),
  delete: <T>(path: string, opts?: { token?: string }) =>
    request<T>("DELETE", path, opts),
};
