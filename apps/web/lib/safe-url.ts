/**
 * Returns the URL if it's a safe absolute http(s) link, otherwise undefined.
 * Use this for every <a href={...}> that displays user- or LLM-supplied content.
 */
export function safeHref(u: string | null | undefined): string | undefined {
  if (!u) return undefined;
  const s = String(u).trim();
  return /^https?:\/\//i.test(s) ? s : undefined;
}

/** Social platforms whose profile links we can build from a bare handle. */
export type SocialPlatform = "telegram" | "linkedin" | "instagram" | "facebook";

const SOCIAL_BASE: Record<SocialPlatform, string> = {
  telegram: "https://t.me/",
  linkedin: "https://linkedin.com/in/",
  instagram: "https://instagram.com/",
  facebook: "https://facebook.com/",
};

/**
 * Turns a social-profile value into a safe clickable href. Managers may enter
 * a full URL (`https://t.me/x`), a bare domain (`t.me/x`), or just a handle
 * (`@x` / `x`) — all become a validated `https://…` link. Returns undefined
 * for empty or unsafe input (so the caller renders no link).
 */
export function socialHref(
  raw: string | null | undefined,
  platform: SocialPlatform,
): string | undefined {
  if (!raw) return undefined;
  const s = String(raw).trim();
  if (!s) return undefined;
  // Already an absolute URL → run through the safety gate.
  if (/^https?:\/\//i.test(s)) return safeHref(s);
  // Looks like a bare domain (t.me/x, linkedin.com/in/x, www.…) → add scheme.
  if (/^(www\.|[a-z0-9-]+\.[a-z]{2,}\/)/i.test(s)) return safeHref(`https://${s}`);
  // Otherwise treat it as a handle: strip leading @ and slashes, then accept
  // only plausible handle characters (letters, digits, dot, underscore, dash).
  const handle = s.replace(/^@+/, "").replace(/^\/+/, "");
  if (!/^[A-Za-z0-9._-]+$/.test(handle)) return undefined;
  return safeHref(`${SOCIAL_BASE[platform]}${handle}`);
}
