import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * Card primitive — taste-soft surface. Wraps the canonical
 * "bg-white border border-brand-border rounded-card" chrome plus the
 * variants in C.card.* into a composable shell.
 *
 *   <Card>
 *     <CardHeader>
 *       <CardTitle>Сегодняшние задачи</CardTitle>
 *       <CardDescription>Что нужно сделать к концу дня.</CardDescription>
 *     </CardHeader>
 *     <CardContent>…</CardContent>
 *     <CardFooter>…</CardFooter>
 *   </Card>
 *
 * NOTE: Every variant string below is an EXACT paste of the corresponding
 * C.card.* token from lib/design-system.ts, minus the "rounded-card"
 * and "border" classes that live in the shared chrome above.
 */
const cardVariants = cva(
  "rounded-card border", // shared chrome
  {
    variants: {
      variant: {
        // Exact mirrors of C.card.* from lib/design-system.ts
        // C.card.base = 'bg-white border border-brand-border rounded-card p-6'
        default: "bg-white border-brand-border",
        // C.card.panel = 'bg-brand-panel border border-brand-border rounded-card p-6'
        panel: "bg-brand-panel border-brand-border",
        // C.card.accent = 'bg-brand-soft border border-brand-accent/20 rounded-card p-6'
        accent: "bg-brand-soft border-brand-accent/20",
        // C.card.dark = 'bg-brand-dark text-white rounded-card p-6'
        dark: "bg-brand-dark text-white border-transparent",
      },
      padding: {
        none: "",
        sm: "p-4",
        default: "p-5 sm:p-6",
        lg: "p-6 sm:p-8",
      },
    },
    defaultVariants: { variant: "default", padding: "default" },
  },
);

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, padding, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(cardVariants({ variant, padding, className }))}
      {...props}
    />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center justify-between gap-2 mb-4", className)}
    {...props}
  />
));
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn("type-card-title text-brand-primary", className)}
    {...props}
  />
));
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("type-caption text-brand-muted", className)}
    {...props}
  />
));
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn(className)} {...props} />
));
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center gap-2 mt-4", className)}
    {...props}
  />
));
CardFooter.displayName = "CardFooter";

export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  cardVariants,
};
