// Shared label maps for Russian-friendly display of backend slugs.
// Add new entries here; components import from this module, not define locally.

// Sprint 3.5 — segment list moved to `lib/constants/segments.ts` so that
// drop-down options + display labels stay in one place. Re-exported here
// for callers that already import from `@/lib/i18n`.
export {
  SEGMENT_LABELS,
  SEGMENT_CHOICES,
  segmentLabel,
} from "@/lib/constants/segments";

export const DEAL_TYPE_LABELS: Record<string, string> = {
  enterprise_direct:   "Enterprise",
  qsr:                 "QSR",
  distributor_partner: "Дистрибьютор",
  raw_materials:       "Сырьё",
  private_small:       "Малый бизнес",
  service_repeat:      "Сервис",
};

export function dealTypeLabel(s: string | null | undefined): string {
  if (!s) return "";
  return DEAL_TYPE_LABELS[s] ?? s;
}

export const PRIORITY_LABELS: Record<string, string> = {
  A: "Приоритет A",
  B: "Приоритет B",
  C: "Приоритет C",
  D: "Приоритет D",
};

export function priorityLabel(p: string | null | undefined): string {
  if (!p) return "";
  return PRIORITY_LABELS[p] ?? `Приоритет ${p}`;
}
