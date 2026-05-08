"use client";

import { ApiError } from "@/lib/api-client";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Auth-aware file download.
 *
 * `window.location.href = '/api/...'` doesn't carry the Supabase Bearer
 * token — that header is only set by the api-client wrapper. Without
 * it, an authed download endpoint returns 401. Solution: fetch as
 * blob with the Authorization header attached, then trigger the
 * native browser download via an in-memory <a download>.
 *
 * Filename is taken from Content-Disposition when present; pass
 * `fallbackFilename` for the case where the server didn't set it.
 */
export async function downloadAuthed(
  apiPath: string,
  fallbackFilename: string,
): Promise<void> {
  const supabase = getSupabaseBrowserClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${apiPath}`, { headers });
  if (!res.ok) {
    let body: unknown = null;
    try {
      const text = await res.text();
      body = text ? JSON.parse(text) : null;
    } catch {
      // Non-JSON error body — surface status code as-is.
    }
    throw new ApiError(res.status, body);
  }

  // Resolve filename: Content-Disposition wins, else caller's hint.
  let filename = fallbackFilename;
  const cd = res.headers.get("Content-Disposition");
  if (cd) {
    const match = cd.match(/filename\*?=(?:UTF-8''|")?([^";]+)"?/i);
    if (match && match[1]) {
      try {
        filename = decodeURIComponent(match[1]);
      } catch {
        filename = match[1];
      }
    }
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Defer revoke so Safari has a tick to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
