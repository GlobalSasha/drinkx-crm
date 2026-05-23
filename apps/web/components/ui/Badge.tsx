import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * Status / category pill primitive. Replaces hand-rolled
 * "type-caption font-semibold px-2 py-0.5 rounded-full ..."
 * strings across the codebase.
 *
 * Variants align with semantic tokens used in the wild:
 *   neutral  — bg-brand-panel text-brand-muted-strong
 *   success  — bg-success/15 text-success (closed-won, healthy, priority A)
 *   success2 — bg-success/10 text-success (priority B)
 *   warning  — bg-warning/10 text-warning (at risk, уточнить)
 *   rose     — bg-rose/10 text-rose (overdue, lost, invalid)
 *   accent   — bg-brand-soft text-brand-accent (brand/default pipeline)
 *   outline  — border border-brand-border text-brand-primary
 */
const badgeVariants = cva(
  // shared chrome — matches the canonical pill literals in the codebase
  "inline-flex items-center gap-1 type-caption font-semibold px-2 py-0.5 rounded-full whitespace-nowrap",
  {
    variants: {
      variant: {
        neutral: "bg-brand-panel text-brand-muted-strong",
        success: "bg-success/15 text-success",
        success2: "bg-success/10 text-success",
        warning: "bg-warning/10 text-warning",
        rose: "bg-rose/10 text-rose",
        accent: "bg-brand-soft text-brand-accent",
        outline: "border border-brand-border text-brand-primary",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(badgeVariants({ variant, className }))}
      {...props}
    />
  ),
);
Badge.displayName = "Badge";

export { Badge, badgeVariants };
