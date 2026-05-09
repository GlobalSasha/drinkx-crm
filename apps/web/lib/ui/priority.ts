// Priority A/B/C/D color palette — Sprint 2.4 G5 centralization.
//
// Pre-G5 there were three local copies (PipelineLeadCard, LeadCard,
// DealTab) with subtly different mappings — A=accent everywhere, but
// B/C/D drifted (success vs warning vs canvas, etc.). Picking one
// canonical mapping kills the drift and makes future palette tweaks
// a one-file edit.
//
// Canonical mapping (matches the prototype + the dominant 2-of-3
// pre-G5 sites):
//   A → accent (purple)   high priority
//   B → success (green)   normal
//   C → warning (amber)   slipping
//   D → muted (grey)      backburner
//
// Two variants per tier:
//   - chip:         soft tinted background + matched text colour, used
//                   for inline badges in lists and headers.
//   - chipBordered: same plus a 30%-alpha border, used in DealTab
//                   where the chip sits on a raised card.

import type { Priority } from "@/lib/types";

interface PriorityVariant {
  /** Soft chip — tinted background + matched text. */
  chip: string;
  /** Same chip with a visible border, for raised-card surfaces. */
  chipBordered: string;
  /** Solid colour — used where the priority is the primary signal
   *  (DealTab tier badges). */
  solid: string;
}

export const priorityConfig: Record<Priority, PriorityVariant> = {
  A: {
    chip: "bg-accent/10 text-accent",
    chipBordered: "bg-accent/10 text-accent border-accent/30",
    solid: "bg-accent text-white",
  },
  B: {
    chip: "bg-success/10 text-success",
    chipBordered: "bg-success/10 text-success border-success/30",
    solid: "bg-success text-white",
  },
  C: {
    chip: "bg-warning/10 text-warning",
    chipBordered: "bg-warning/10 text-warning border-warning/30",
    solid: "bg-warning text-white",
  },
  D: {
    chip: "bg-black/5 text-muted",
    chipBordered: "bg-black/5 text-muted border-black/10",
    solid: "bg-muted text-white",
  },
};

/** Fallback used when a priority value comes back as null / unknown
 *  string (defensive — codepath that mostly trips during data import). */
export const PRIORITY_FALLBACK_CHIP = "bg-black/5 text-muted";

/** Convenience: get the chip class for a priority, falling back to
 *  the unknown-state style. Accepts string for the (rare) cases where
 *  the type isn't narrowed yet. */
export function priorityChip(p: string | null | undefined): string {
  if (p && p in priorityConfig) {
    return priorityConfig[p as Priority].chip;
  }
  return PRIORITY_FALLBACK_CHIP;
}
