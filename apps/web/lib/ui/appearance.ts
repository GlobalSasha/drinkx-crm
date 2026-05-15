/**
 * Appearance presets — mapping the per-user UI prefs (see UiPrefs in
 * lib/types) to concrete CSS values. Backend stores the preset keys
 * (e.g. "graphite"), `<ThemeApplier/>` resolves them to CSS custom
 * properties on :root.
 *
 * Why CSS vars: a single source of truth that AppShell / globals.css /
 * any consuming component reads. Changing the preset is a property
 * write, not a tree-wide re-render.
 */
import type {
  BackgroundColor,
  Density,
  FontSize,
  SidebarColor,
} from "@/lib/types";

export interface SidebarPreset {
  key: SidebarColor;
  label: string;
  /** Background color of the sidebar (--sidebar-bg). */
  bg: string;
  /** Text color inside the sidebar (--sidebar-fg). */
  fg: string;
  /** Border color separating sidebar from main content. */
  border: string;
  /** Background of the hover/active pill behind nav rows. */
  hover: string;
}

export const SIDEBAR_PRESETS: Record<SidebarColor, SidebarPreset> = {
  white: {
    key: "white",
    label: "Молочный",
    bg: "#FFFFFF",
    fg: "#111111",
    border: "#D6D4CE",
    hover: "rgba(0,0,0,0.04)",
  },
  cream: {
    key: "cream",
    label: "Кремовый",
    bg: "#F5F4F0",
    fg: "#111111",
    border: "#D6D4CE",
    hover: "rgba(0,0,0,0.05)",
  },
  beige: {
    key: "beige",
    label: "Бежевый",
    bg: "#E5E3DC",
    fg: "#111111",
    border: "#C9C6BE",
    hover: "rgba(0,0,0,0.06)",
  },
  graphite: {
    key: "graphite",
    label: "Графит",
    bg: "#111111",
    fg: "#F5F4F0",
    border: "rgba(255,255,255,0.10)",
    hover: "rgba(255,255,255,0.08)",
  },
  coffee: {
    key: "coffee",
    label: "Кофейный",
    bg: "#3D2817",
    fg: "#F5F4F0",
    border: "rgba(255,255,255,0.10)",
    hover: "rgba(255,255,255,0.07)",
  },
};

export interface BackgroundPreset {
  key: BackgroundColor;
  label: string;
  bg: string;
}

export const BACKGROUND_PRESETS: Record<BackgroundColor, BackgroundPreset> = {
  cream: { key: "cream", label: "Кремовый", bg: "#F5F4F0" },
  white: { key: "white", label: "Белый", bg: "#FFFFFF" },
};

export const DENSITY_LABELS: Record<Density, string> = {
  comfortable: "Стандартная",
  compact: "Компактная",
};

/** Multiplier applied to padding utilities via --density-scale. */
export const DENSITY_SCALE: Record<Density, string> = {
  comfortable: "1",
  compact: "0.75",
};

export const FONT_SIZE_LABELS: Record<FontSize, string> = {
  sm: "Мелкий",
  md: "Стандартный",
  lg: "Крупный",
};

/** Base font size override; consumed by --base-font-size on :root. */
export const FONT_SIZE_PX: Record<FontSize, string> = {
  sm: "13px",
  md: "14px",
  lg: "16px",
};

export const UI_PREFS_DEFAULTS = {
  sidebar_color: "white" as SidebarColor,
  background_color: "cream" as BackgroundColor,
  density: "comfortable" as Density,
  font_size: "md" as FontSize,
};
