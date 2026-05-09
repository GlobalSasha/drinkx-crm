"use client";
// /settings — Sprint 2.3 G3.
//
// Left sidebar with sections, main content renders the active one.
// Only «Воронки» is live in v1; the rest are roadmap stubs (per the
// G3 spec: «Скоро» for Phase 2.4+). Read access is open to all roles;
// PipelinesSection internally gates write actions on useMe().role.
import { useState } from "react";
import {
  BellRing,
  Bot,
  ChevronDown,
  KeyRound,
  Plug,
  ScrollText,
  Settings as SettingsIcon,
  Sparkles,
  Split,
  User,
  Users,
} from "lucide-react";
import clsx from "clsx";

import { AISection } from "@/components/settings/AISection";
import { ChannelsSection } from "@/components/settings/ChannelsSection";
import { CustomFieldsSection } from "@/components/settings/CustomFieldsSection";
import { PipelinesSection } from "@/components/settings/PipelinesSection";
import { TeamSection } from "@/components/settings/TeamSection";
import { TemplatesSection } from "@/components/settings/TemplatesSection";

type SectionKey =
  | "pipelines"
  | "profile"
  | "team"
  | "channels"
  | "ai"
  | "custom_fields"
  | "templates"
  | "notifications"
  | "api";

interface SectionDef {
  key: SectionKey;
  label: string;
  icon: React.ReactNode;
  /** Live in v1 vs «Скоро» roadmap stub. */
  ready: boolean;
}

const SECTIONS: SectionDef[] = [
  { key: "pipelines",     label: "Воронки",      icon: <Split size={15} />,    ready: true  },
  { key: "team",          label: "Команда",      icon: <Users size={15} />,    ready: true  },
  { key: "channels",      label: "Каналы",       icon: <Plug size={15} />,     ready: true  },
  { key: "ai",            label: "AI",           icon: <Bot size={15} />,      ready: true  },
  { key: "custom_fields", label: "Кастомные поля", icon: <Sparkles size={15} />, ready: true },
  { key: "templates",     label: "Шаблоны",      icon: <ScrollText size={15} />, ready: true },
  { key: "profile",       label: "Профиль",      icon: <User size={15} />,     ready: false },
  { key: "notifications", label: "Уведомления",  icon: <BellRing size={15} />, ready: false },
  { key: "api",           label: "API",          icon: <KeyRound size={15} />, ready: false },
];

export default function SettingsPage() {
  const [active, setActive] = useState<SectionKey>("pipelines");

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
      {/* Page header */}
      <div className="flex items-center gap-2 mb-6">
        <SettingsIcon size={20} className="text-muted" />
        <h1 className="text-xl font-extrabold tracking-tight">Настройки</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[200px_minmax(0,1fr)] gap-6">
        {/* Sidebar — Sprint 2.6 G3: «Скоро» entries fold into a
            <details> disclosure (collapsed by default) so the active
            sections sit alone at the top. Reduces the visual weight
            of three roadmap stubs (Профиль / Уведомления / API)
            without removing them from the IA. */}
        <nav className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible">
          {SECTIONS.filter((s) => s.ready).map((s) => {
            const isActive = active === s.key;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => setActive(s.key)}
                className={clsx(
                  "flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold whitespace-nowrap transition-colors",
                  isActive
                    ? "bg-accent/10 text-accent"
                    : "text-muted hover:bg-black/5 hover:text-ink",
                )}
              >
                {s.icon}
                <span className="flex-1 text-left">{s.label}</span>
              </button>
            );
          })}

          {/* Roadmap stubs — collapsed by default. `<details>` is
              built-in so no third-party dep; we style the marker via
              the `[&::-webkit-details-marker]:hidden` pseudo (handled
              by the explicit ChevronDown rotation below). */}
          {SECTIONS.some((s) => !s.ready) && (
            <details className="group mt-1 md:mt-2 hidden md:block">
              <summary
                className="flex items-center gap-2 px-3 py-2 rounded-xl text-[11px] font-mono uppercase tracking-[0.18em] text-muted-3 cursor-pointer list-none hover:bg-black/5 hover:text-muted [&::-webkit-details-marker]:hidden"
              >
                <ChevronDown
                  size={12}
                  className="transition-transform duration-200 group-open:rotate-180"
                />
                <span className="flex-1 text-left">Скоро</span>
                <span className="text-[9px] font-mono normal-case tracking-normal bg-black/5 rounded-pill px-1.5 py-0.5">
                  {SECTIONS.filter((s) => !s.ready).length}
                </span>
              </summary>
              {SECTIONS.filter((s) => !s.ready).map((s) => (
                <div
                  key={s.key}
                  className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold whitespace-nowrap text-muted-3 cursor-not-allowed"
                  aria-disabled="true"
                >
                  {s.icon}
                  <span className="flex-1 text-left">{s.label}</span>
                </div>
              ))}
            </details>
          )}

          {/* Mobile: keep the original flat list with «скоро» chips —
              <details> wouldn't gracefully fit a horizontal scroller. */}
          <div className="contents md:hidden">
            {SECTIONS.filter((s) => !s.ready).map((s) => (
              <button
                key={`mobile-${s.key}`}
                type="button"
                disabled
                className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold whitespace-nowrap text-muted-3 cursor-not-allowed"
              >
                {s.icon}
                <span className="flex-1 text-left">{s.label}</span>
              </button>
            ))}
          </div>
        </nav>

        {/* Main */}
        <main className="min-w-0">
          {active === "pipelines" && <PipelinesSection />}
          {active === "team" && <TeamSection />}
          {active === "channels" && <ChannelsSection />}
          {active === "ai" && <AISection />}
          {active === "custom_fields" && <CustomFieldsSection />}
          {active === "templates" && <TemplatesSection />}
          {active !== "pipelines" &&
            active !== "team" &&
            active !== "channels" &&
            active !== "ai" &&
            active !== "custom_fields" &&
            active !== "templates" && (
              <div className="bg-canvas/60 border border-black/5 rounded-2xl px-6 py-12 text-center">
                <p className="text-sm text-muted">Эта секция появится позже.</p>
              </div>
            )}
        </main>
      </div>
    </div>
  );
}
