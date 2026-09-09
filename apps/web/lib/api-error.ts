// Бэкенд шлёт detail тремя формами: строка, {code, message} или массив
// (Pydantic 422) — этот хелпер сводит их к одной строке для UI.
import { ApiError } from "@/lib/api-client";

export function apiErrorDetail(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  const body = err.body;
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return fallback;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}
