import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * PageContainer — the single page frame for every top-level screen.
 *
 * Before this primitive, each page rolled its own wrapper, so the same
 * kind of screen rendered at different widths (max-w-6xl / 1280 / 1100 /
 * 920…) with different padding (px-4 sm:px-6 vs px-6, py-6 vs py-6 sm:py-8),
 * which made content "jump" when navigating between sections.
 *
 * This centralises the outer frame: one horizontal/vertical rhythm, and a
 * small fixed set of named widths. New pages should wrap their content in
 * <PageContainer>. The `pageContainerVariants` export lets existing pages
 * adopt the same frame at the className level without restructuring JSX.
 *
 *   <PageContainer>…</PageContainer>            // standard list/admin screen
 *   <PageContainer width="wide">…</PageContainer>   // dashboards
 *   <PageContainer width="narrow">…</PageContainer> // focused forms / reading
 */
const pageContainerVariants = cva(
  // shared frame: centred, full-bleed-safe, consistent gutters + vertical rhythm
  "mx-auto w-full px-4 sm:px-6 py-6 sm:py-8",
  {
    variants: {
      width: {
        narrow: "max-w-3xl", // 768px — focused forms, short reading pages
        content: "max-w-4xl", // 896px — single-column content
        default: "max-w-6xl", // 1152px — standard list / admin screens
        wide: "max-w-[1280px]", // dashboards, dense overviews
        full: "max-w-[1800px]", // boards / near full-bleed
      },
    },
    defaultVariants: { width: "default" },
  },
);

export type PageWidth = NonNullable<VariantProps<typeof pageContainerVariants>["width"]>;

export interface PageContainerProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof pageContainerVariants> {}

const PageContainer = React.forwardRef<HTMLDivElement, PageContainerProps>(
  ({ className, width, ...props }, ref) => (
    <div ref={ref} className={cn(pageContainerVariants({ width, className }))} {...props} />
  ),
);
PageContainer.displayName = "PageContainer";

export { PageContainer, pageContainerVariants };
