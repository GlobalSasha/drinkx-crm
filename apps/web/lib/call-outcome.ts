/**
 * «Как прошёл звонок?» — the CRM can't see the call itself, so a tap on
 * «Позвонить» remembers it, and when the manager comes back to the card
 * the card asks for the result. Per-tab (sessionStorage); storage errors
 * just mean no question is asked.
 */
const KEY = "drinkx:pending-call";
/** Shorter than this — the manager came straight back, no real call. */
export const MIN_CALL_MS = 5_000;
/** Older than this — stale, don't ask about a call from this morning. */
export const MAX_CALL_MS = 2 * 60 * 60 * 1000;

export function markPendingCall(leadId: string, now: number = Date.now()): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify({ leadId, at: now }));
  } catch {
    /* storage unavailable */
  }
}

/** True once per call: a pending call for this lead that lasted long
 *  enough and isn't stale. Consumes the mark either way once it's ripe
 *  or stale, so the question never repeats. */
export function takePendingCall(leadId: string, now: number = Date.now()): boolean {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return false;
    const { leadId: id, at } = JSON.parse(raw) as { leadId?: string; at?: number };
    if (id !== leadId || typeof at !== "number") return false;
    const elapsed = now - at;
    if (elapsed < MIN_CALL_MS) return false;
    window.sessionStorage.removeItem(KEY);
    return elapsed <= MAX_CALL_MS;
  } catch {
    return false;
  }
}

export type CallOutcome = "reached" | "no_answer" | "call_back";

/** What the composer gets for each answer. Nothing is saved until the
 *  manager presses «Отправить». */
export const OUTCOME_PREFILL: Record<CallOutcome, { mode: "call" | "task"; text: string }> = {
  reached: { mode: "call", text: "Дозвонился. " },
  no_answer: { mode: "call", text: "Не дозвонился" },
  call_back: { mode: "task", text: "Перезвонить" },
};
