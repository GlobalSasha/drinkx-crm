"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * Button primitive. Wraps the existing C.button.* token strings from
 * lib/design-system.ts into CVA variants so callers don't repeat 80+
 * character className literals.
 *
 *   <Button>Сохранить</Button>                       // primary, default size
 *   <Button variant="ghost" size="sm">Отмена</Button>
 *   <Button variant="destructive">Удалить</Button>
 *   <Button asChild><Link href="/x">Открыть</Link></Button>
 *
 * `asChild` lets you compose with Next.js Link or other components that
 * own their root element.
 *
 * NOTE: Every variant string below is an EXACT copy of the corresponding
 * C.button.* entry from lib/design-system.ts. The focus rings and font-medium
 * are already embedded in those strings — the shared chrome intentionally
 * omits them to avoid Tailwind class conflicts.
 */
const buttonVariants = cva(
  // Shared chrome: layout only. Focus ring + font weight live inside each
  // C.button.* variant string to stay byte-identical to hand-rolled usage.
  "inline-flex items-center justify-center gap-1.5 transition-colors disabled:opacity-40 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        // Exact mirrors of C.button.* from lib/design-system.ts
        primary:
          "bg-brand-accent text-white rounded-full font-medium transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg",
        ghost:
          "bg-transparent text-brand-muted border border-brand-border rounded-full font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg",
        pill:
          "bg-brand-panel text-brand-muted-strong border border-brand-border rounded-full font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg",
        nav:
          "bg-brand-panel text-brand-primary rounded-full font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg",
        // New variants (no matching C.button.* token — explicitly documented)
        destructive:
          "text-rose bg-rose/10 hover:bg-rose/15 rounded-full font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg",
        link:
          "text-brand-accent underline-offset-2 hover:underline rounded-md font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1",
      },
      size: {
        default: "px-4 py-2 type-body",
        sm: "px-3 py-1.5 type-caption",
        lg: "px-5 py-2.5 type-body",
        icon: "w-9 h-9 p-0",
      },
    },
    defaultVariants: { variant: "primary", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
