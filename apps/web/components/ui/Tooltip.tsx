"use client";

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/cn";

/**
 * Tooltip primitive — Radix-backed. Use sparingly on icon-only
 * controls (the «⋯» menu, the paperclip toggle, etc.) so the affordance
 * isn't a mystery.
 *
 *   <TooltipProvider>
 *     <Tooltip>
 *       <TooltipTrigger asChild>
 *         <button …><MoreHorizontal /></button>
 *       </TooltipTrigger>
 *       <TooltipContent>Ещё действия</TooltipContent>
 *     </Tooltip>
 *   </TooltipProvider>
 *
 * Wrap a section of the app with <TooltipProvider> once (e.g. at the
 * layout level) — the individual tooltips don't each need one.
 */
const TooltipProvider = TooltipPrimitive.Provider;
const Tooltip = TooltipPrimitive.Root;
const TooltipTrigger = TooltipPrimitive.Trigger;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 px-2.5 py-1.5 rounded-lg bg-brand-primary text-white type-caption font-medium shadow-overlay",
        // Вход из точки вызова (origin от Radix); выход мгновенный — тише входа.
        "data-[state=delayed-open]:animate-[overlayIn_125ms_cubic-bezier(0.32,0.72,0,1)]",
        "origin-[var(--radix-tooltip-content-transform-origin)]",
        className,
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
