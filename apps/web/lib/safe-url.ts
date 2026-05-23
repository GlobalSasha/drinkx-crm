/**
 * Returns the URL if it's a safe absolute http(s) link, otherwise undefined.
 * Use this for every <a href={...}> that displays user- or LLM-supplied content.
 */
export function safeHref(u: string | null | undefined): string | undefined {
  if (!u) return undefined;
  const s = String(u).trim();
  return /^https?:\/\//i.test(s) ? s : undefined;
}
