import * as React from "react";
import { cn } from "@/lib/cn";

/**
 * PageHeader — the single section header for every top-level screen.
 *
 * Before this, each page hand-rolled its title row, so the title style drifted
 * (type-page-title vs type-card-title vs text-xl font-bold vs text-lg), the
 * bottom margin varied (mb-5 / mb-6 / mb-8), and the icon/subtitle/actions
 * layout was reinvented per page. This pins all of that down:
 *   • one title style (type-page-title)
 *   • one rhythm (mb-6)
 *   • icon left of the title, optional subtitle under it, optional actions right
 *
 *   <PageHeader icon={<Users size={20} />} title="Команда" />
 *   <PageHeader title="Прогноз" subtitle="Взвешенный прогноз по этапам" />
 *   <PageHeader title="Компании" icon={<Building2 size={20} />} actions={<Count/>} />
 */
export interface PageHeaderProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Icon element (e.g. a lucide icon). Rendered left of the title. */
  icon?: React.ReactNode;
  /** Right-aligned actions: buttons, counts, toggles, filters. */
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, subtitle, icon, actions, className }: PageHeaderProps) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3 mb-6", className)}>
      <div className="min-w-0">
        <h1 className="type-page-title text-brand-primary flex items-center gap-2">
          {icon ? <span className="text-brand-muted shrink-0">{icon}</span> : null}
          {title}
        </h1>
        {subtitle ? <p className="type-body text-brand-muted mt-1">{subtitle}</p> : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>
      ) : null}
    </div>
  );
}
