"use client";

import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/cn";

/**
 * Tabs primitive — Radix-backed for ARIA + keyboard nav (Tab, arrows,
 * Home/End come for free). Visual matches the existing hand-rolled
 * LeadCard tab strip: pill-padded triggers with an orange bottom-border
 * indicator on the active tab.
 *
 *   <Tabs value={tab} onValueChange={setTab}>
 *     <TabsList>
 *       <TabsTrigger value="activity">Активность</TabsTrigger>
 *       <TabsTrigger value="contacts">Контакты</TabsTrigger>
 *     </TabsList>
 *     <TabsContent value="activity">…</TabsContent>
 *     <TabsContent value="contacts">…</TabsContent>
 *   </Tabs>
 */
const Tabs = TabsPrimitive.Root;

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "flex gap-0 border-b border-brand-border -mb-px overflow-x-auto",
      className,
    )}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "px-4 py-2.5 type-caption font-semibold border-b-2 transition-colors duration-200 whitespace-nowrap",
      "border-transparent text-brand-muted",
      "data-[state=active]:border-brand-accent data-[state=active]:text-brand-accent-text",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 rounded-sm",
      "disabled:opacity-40 disabled:pointer-events-none",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn("focus-visible:outline-none", className)}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
