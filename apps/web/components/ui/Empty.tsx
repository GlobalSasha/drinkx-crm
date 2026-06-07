import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * Empty-state primitive. Use anywhere a list, table, or card surface
 * has nothing to show — a search returned no hits, no tasks today,
 * no integrations yet, etc.
 *
 * <Empty>
 *   <EmptyHeader>
 *     <EmptyMedia variant="icon"><ListChecks /></EmptyMedia>
 *     <EmptyTitle>Задач нет</EmptyTitle>
 *     <EmptyDescription>
 *       Поставьте первую задачу, чтобы она появилась здесь.
 *     </EmptyDescription>
 *   </EmptyHeader>
 *   <EmptyContent>
 *     <button …>Поставить задачу</button>
 *   </EmptyContent>
 * </Empty>
 */
function Empty({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="empty"
      className={cn(
        "flex min-w-0 flex-1 flex-col items-center justify-center gap-6 rounded-card border border-dashed border-brand-border bg-white p-6 text-center text-balance md:p-12",
        className,
      )}
      {...props}
    />
  );
}

function EmptyHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="empty-header"
      className={cn("flex max-w-sm flex-col items-center gap-2 text-center", className)}
      {...props}
    />
  );
}

const emptyMediaVariants = cva(
  "mb-2 flex shrink-0 items-center justify-center [&_svg:not([class*='size-'])]:size-6 [&_svg]:pointer-events-none",
  {
    variants: {
      variant: {
        default: "bg-transparent",
        icon: "size-10 rounded-full bg-brand-panel text-brand-primary [&_svg:not([class*='size-'])]:size-5",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

function EmptyMedia({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof emptyMediaVariants>) {
  return (
    <div
      data-slot="empty-icon"
      data-variant={variant}
      className={cn(emptyMediaVariants({ variant, className }))}
      {...props}
    />
  );
}

function EmptyTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="empty-title"
      className={cn("type-card-title text-brand-primary", className)}
      {...props}
    />
  );
}

function EmptyDescription({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="empty-description"
      className={cn(
        "type-body text-brand-muted [&>a]:underline [&>a]:underline-offset-2 [&>a:hover]:text-brand-accent",
        className,
      )}
      {...props}
    />
  );
}

function EmptyContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="empty-content"
      className={cn("flex w-full max-w-sm min-w-0 flex-col items-center justify-center gap-3 text-balance", className)}
      {...props}
    />
  );
}

export { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription, EmptyContent };
