import * as React from "react";
import { cn } from "@/lib/cn";

/**
 * Keyboard shortcut hint. Render inline next to actions that have
 * a shortcut, e.g.:
 *
 *   Поиск <Kbd>⌘K</Kbd>
 *
 * Group multiple keys with KbdGroup.
 */
function Kbd({ className, ...props }: React.ComponentProps<"kbd">) {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center gap-1 rounded-md bg-brand-panel px-1.5 type-caption font-mono text-brand-muted",
        "[&_svg:not([class*='size-'])]:size-3",
        className,
      )}
      {...props}
    />
  );
}

function KbdGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="kbd-group"
      className={cn("inline-flex items-center gap-1", className)}
      {...props}
    />
  );
}

export { Kbd, KbdGroup };
