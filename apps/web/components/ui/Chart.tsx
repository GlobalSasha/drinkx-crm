"use client";

import * as React from "react";
import {
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
} from "recharts";
import { cn } from "@/lib/cn";

/**
 * Chart primitives — brand-themed wrappers around recharts. Use these
 * everywhere a chart appears so we don't accumulate OKLCH-on-cream
 * pixel disasters (per the sales-ops audit).
 *
 * Palette: warm orange + 4 grays. Imported by callers as
 * `import { BRAND_CHART_COLORS } from "@/components/ui/Chart"`.
 *
 *   <ChartContainer height={240}>
 *     <BarChart data={data}>
 *       <Bar dataKey="value" fill={BRAND_CHART_COLORS[0]} radius={[6,6,0,0]} />
 *       <ChartTooltip />
 *     </BarChart>
 *   </ChartContainer>
 */

/** Primary palette — orange-led + warm neutral grays. Index 0 is the
 *  brand accent. Use slot 1+ for secondary series. */
export const BRAND_CHART_COLORS = [
  "#FF4E00", // brand-accent
  "#1A1A1A", // brand-primary
  "#B7672D", // warning (warm brown-orange)
  "#6B6B6B", // brand-muted
  "#D6D4CE", // brand-border (lightest)
] as const;

/** Subdued grid color — matches our brand-border but slightly lighter for grids. */
export const CHART_GRID_COLOR = "#E5E3DC"; // brand-panel
export const CHART_AXIS_COLOR = "#6B6B6B"; // brand-muted

interface ChartContainerProps {
  children: React.ReactElement;
  height?: number;
  className?: string;
  "aria-label"?: string;
}

/** Responsive container with a fixed pixel height. Wraps the recharts
 *  chart so it fills its parent's width. */
export function ChartContainer({
  children,
  height = 240,
  className,
  ...rest
}: ChartContainerProps) {
  return (
    <div
      className={cn("w-full", className)}
      style={{ height }}
      role="img"
      {...rest}
    >
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

type TooltipExtras = Partial<React.ComponentProps<typeof RechartsTooltip>>;

/** Cream-themed tooltip surface — replaces recharts' default dark popover.
 *  Drop this inside any chart instead of <Tooltip /> from recharts directly. */
export function ChartTooltip(props: TooltipExtras) {
  return (
    <RechartsTooltip
      cursor={{ fill: "rgba(255, 78, 0, 0.05)" }}
      contentStyle={{
        backgroundColor: "#F5F4F0", // brand-bg
        border: "1px solid #D6D4CE", // brand-border
        borderRadius: "1rem",
        boxShadow: "0 8px 24px -8px rgba(17, 17, 17, 0.08)", // shadow-soft equivalent
        padding: "10px 12px",
        fontFamily: "var(--font-ui, system-ui)",
      }}
      labelStyle={{
        color: "#6B6B6B", // brand-muted
        fontSize: "11px",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.04em",
        marginBottom: "4px",
      }}
      itemStyle={{
        color: "#111111", // brand-primary
        fontSize: "14px",
        fontWeight: 500,
        padding: 0,
      }}
      {...props}
    />
  );
}

/** Standard horizontal-bar variant tooltip — same chrome, single-line item
 *  formatted as "Label · value". Use when a series doesn't need a header label. */
export function ChartTooltipCompact(props: TooltipExtras) {
  return (
    <ChartTooltip
      labelFormatter={() => ""}  // hide label
      {...props}
    />
  );
}
