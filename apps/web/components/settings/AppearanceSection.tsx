"use client";

// AppearanceSection — Settings → Внешний вид.
//
// Lets each manager pick a sidebar color preset, page background,
// density, and base font size. Saves to /auth/me/ui-prefs which
// updates the user's row and broadcasts the new MeOut into the
// `me` query cache; <ThemeApplier/> picks up the change and writes
// fresh CSS variables to :root immediately — no reload needed.

import { Loader2 } from "lucide-react";

import { useMe } from "@/lib/hooks/use-me";
import { useUpdateUiPrefs } from "@/lib/hooks/use-ui-prefs";
import type {
  BackgroundColor,
  Density,
  FontSize,
  SidebarColor,
} from "@/lib/types";
import {
  BACKGROUND_PRESETS,
  DENSITY_LABELS,
  FONT_SIZE_LABELS,
  FONT_SIZE_PX,
  SIDEBAR_PRESETS,
  UI_PREFS_DEFAULTS,
} from "@/lib/ui/appearance";

export function AppearanceSection() {
  const me = useMe();
  const update = useUpdateUiPrefs();
  const prefs = me.data?.ui_prefs ?? UI_PREFS_DEFAULTS;

  return (
    <div className="space-y-8 max-w-3xl">
      <header>
        <h2 className="text-lg font-bold tracking-tight mb-1">Внешний вид</h2>
        <p className="text-sm text-muted">
          Эти настройки видите только вы. Сохраняются в профиль и
          синхронизируются между устройствами.
        </p>
      </header>

      {/* Sidebar color */}
      <section>
        <h3 className="text-sm font-semibold mb-2">Цвет боковой панели</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {(Object.keys(SIDEBAR_PRESETS) as SidebarColor[]).map((key) => {
            const p = SIDEBAR_PRESETS[key];
            const active = prefs.sidebar_color === key;
            return (
              <button
                key={key}
                type="button"
                disabled={update.isPending}
                onClick={() => update.mutate({ sidebar_color: key })}
                className={`relative rounded-2xl border p-3 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 ${
                  active
                    ? "border-brand-accent ring-2 ring-brand-accent/30"
                    : "border-black/10 hover:border-black/20"
                }`}
                aria-pressed={active}
              >
                <div
                  className="w-full h-14 rounded-xl mb-2 border"
                  style={{ backgroundColor: p.bg, borderColor: p.border }}
                />
                <p className="text-xs font-semibold">{p.label}</p>
              </button>
            );
          })}
        </div>
      </section>

      {/* Background */}
      <section>
        <h3 className="text-sm font-semibold mb-2">Фон страниц</h3>
        <div className="grid grid-cols-2 sm:max-w-md gap-3">
          {(Object.keys(BACKGROUND_PRESETS) as BackgroundColor[]).map((key) => {
            const p = BACKGROUND_PRESETS[key];
            const active = prefs.background_color === key;
            return (
              <button
                key={key}
                type="button"
                disabled={update.isPending}
                onClick={() => update.mutate({ background_color: key })}
                className={`rounded-2xl border p-3 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 ${
                  active
                    ? "border-brand-accent ring-2 ring-brand-accent/30"
                    : "border-black/10 hover:border-black/20"
                }`}
                aria-pressed={active}
              >
                <div
                  className="w-full h-14 rounded-xl mb-2 border border-black/10"
                  style={{ backgroundColor: p.bg }}
                />
                <p className="text-xs font-semibold">{p.label}</p>
              </button>
            );
          })}
        </div>
      </section>

      {/* Density */}
      <section>
        <h3 className="text-sm font-semibold mb-2">Плотность</h3>
        <p className="text-xs text-muted-2 mb-2">
          Компактный режим уменьшает внутренние отступы — больше
          информации помещается на экране.
        </p>
        <div className="inline-flex rounded-pill bg-black/5 p-1">
          {(["comfortable", "compact"] as Density[]).map((key) => {
            const active = prefs.density === key;
            return (
              <button
                key={key}
                type="button"
                disabled={update.isPending}
                onClick={() => update.mutate({ density: key })}
                className={`px-4 py-1.5 rounded-pill text-sm font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
                  active
                    ? "bg-white text-ink shadow-soft"
                    : "text-muted hover:text-ink"
                }`}
                aria-pressed={active}
              >
                {DENSITY_LABELS[key]}
              </button>
            );
          })}
        </div>
      </section>

      {/* Font size */}
      <section>
        <h3 className="text-sm font-semibold mb-2">Размер шрифта</h3>
        <p className="text-xs text-muted-2 mb-2">
          Применяется ко всем экранам приложения.
        </p>
        <div className="inline-flex rounded-pill bg-black/5 p-1">
          {(["sm", "md", "lg"] as FontSize[]).map((key) => {
            const active = prefs.font_size === key;
            return (
              <button
                key={key}
                type="button"
                disabled={update.isPending}
                onClick={() => update.mutate({ font_size: key })}
                className={`px-4 py-1.5 rounded-pill font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
                  active
                    ? "bg-white text-ink shadow-soft"
                    : "text-muted hover:text-ink"
                }`}
                style={{ fontSize: FONT_SIZE_PX[key] }}
                aria-pressed={active}
              >
                {FONT_SIZE_LABELS[key]}
              </button>
            );
          })}
        </div>
      </section>

      {/* Save indicator */}
      <div className="text-xs text-muted-3 h-4 flex items-center gap-1.5">
        {update.isPending && (
          <>
            <Loader2 size={11} className="animate-spin" />
            Сохраняем…
          </>
        )}
        {update.isSuccess && !update.isPending && (
          <span className="text-success">Сохранено</span>
        )}
        {update.isError && (
          <span className="text-rose">Не удалось сохранить</span>
        )}
      </div>
    </div>
  );
}
