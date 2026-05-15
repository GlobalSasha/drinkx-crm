"use client";

import { useEffect } from "react";
import { useMe } from "@/lib/hooks/use-me";
import {
  BACKGROUND_PRESETS,
  DENSITY_SCALE,
  FONT_SIZE_PX,
  SIDEBAR_PRESETS,
  UI_PREFS_DEFAULTS,
} from "@/lib/ui/appearance";

/**
 * Reads the current user's `ui_prefs` from /auth/me and writes them
 * as CSS custom properties on `documentElement`. Consumers
 * (AppShell sidebar, body background, etc.) read those variables, so
 * a single useMe()-driven write here flips the entire app theme
 * without prop-drilling.
 *
 * Mounted once at the (app) layout level. No SSR concerns — CSS vars
 * write happens in useEffect, before the variables are set Tailwind
 * fallbacks render exactly the previous behaviour (white sidebar,
 * cream page).
 */
export function ThemeApplier() {
  const me = useMe();
  const prefs = me.data?.ui_prefs ?? UI_PREFS_DEFAULTS;

  useEffect(() => {
    const root = document.documentElement;
    const sidebar = SIDEBAR_PRESETS[prefs.sidebar_color] ?? SIDEBAR_PRESETS.white;
    const bg = BACKGROUND_PRESETS[prefs.background_color] ?? BACKGROUND_PRESETS.cream;

    root.style.setProperty("--sidebar-bg", sidebar.bg);
    root.style.setProperty("--sidebar-fg", sidebar.fg);
    root.style.setProperty("--sidebar-border", sidebar.border);
    root.style.setProperty("--sidebar-hover", sidebar.hover);
    root.style.setProperty("--page-bg", bg.bg);
    root.style.setProperty("--density-scale", DENSITY_SCALE[prefs.density] ?? "1");
    root.style.setProperty("--base-font-size", FONT_SIZE_PX[prefs.font_size] ?? "14px");
  }, [
    prefs.sidebar_color,
    prefs.background_color,
    prefs.density,
    prefs.font_size,
  ]);

  return null;
}
