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
  KeyRound,
  Plug,
  Settings as SettingsIcon,
  Split,
  User,
  Users,
} from "lucide-react";
import clsx from "clsx";

import { PipelinesSection } from "@/components/settings/PipelinesSection";
import { TeamSection } from "@/components/settings/TeamSection";

type SectionKey =
  | "pipelines"
  | "profile"
  | "team"
  | "notifications"
  | "integrations"
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
  { key: "profile",       label: "Профиль",      icon: <User size={15} />,     ready: false },
  { key: "notifications", label: "Уведомления",  icon: <BellRing size={15} />, ready: false },
  { key: "integrations",  label: "Интеграции",   icon: <Plug size={15} />,     ready: false },
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
        {/* Sidebar */}
        <nav className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible">
          {SECTIONS.map((s) => {
            const isActive = active === s.key;
            const isClickable = s.ready;
            return (
              <button
                key={s.key}
                type="button"
                onClick={isClickable ? () => setActive(s.key) : undefined}
                disabled={!isClickable}
                className={clsx(
                  "flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold whitespace-nowrap transition-colors",
                  isActive
                    ? "bg-accent/10 text-accent"
                    : isClickable
                      ? "text-muted hover:bg-black/5 hover:text-ink"
                      : "text-muted-3 cursor-not-allowed",
                )}
              >
                {s.icon}
                <span className="flex-1 text-left">{s.label}</span>
                {!s.ready && (
                  <span className="hidden md:inline text-[9px] font-mono uppercase tracking-wide bg-black/5 text-muted-3 rounded-pill px-1.5 py-0.5">
                    скоро
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Main */}
        <main className="min-w-0">
          {active === "pipelines" && <PipelinesSection />}
          {active === "team" && <TeamSection />}
          {active !== "pipelines" && active !== "team" && (
            <div className="bg-canvas/60 border border-black/5 rounded-2xl px-6 py-12 text-center">
              <p className="text-sm text-muted">Эта секция появится позже.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
