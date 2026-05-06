"use client";
import { useEffect } from "react";
import Link from "next/link";
import { X, ChevronLeft, ChevronRight, ArrowRight, AlertTriangle, CheckCircle2 } from "lucide-react";
import { usePipelineStore } from "@/lib/store/pipeline-store";
import type { LeadOut } from "@/lib/types";

const PRIORITY_COLORS: Record<string, string> = {
  A: "text-accent bg-accent/10",
  B: "text-success bg-success/10",
  C: "text-warning bg-warning/10",
  D: "text-muted bg-black/5",
};

const DEAL_TYPE_LABELS: Record<string, string> = {
  new: "Новый",
  upsell: "Upsell",
  renewal: "Renewal",
  partner: "Партнёр",
};

export function BriefDrawer() {
  const { selectedLead, closeDrawer, navigateDrawer, visibleLeads } =
    usePipelineStore();

  const currentIndex = selectedLead
    ? visibleLeads.findIndex((l) => l.id === selectedLead.id)
    : -1;
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < visibleLeads.length - 1;

  // Keyboard nav
  useEffect(() => {
    if (!selectedLead) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeDrawer();
      if (e.key === "ArrowLeft" && hasPrev) navigateDrawer(-1);
      if (e.key === "ArrowRight" && hasNext) navigateDrawer(1);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [selectedLead, closeDrawer, navigateDrawer, hasPrev, hasNext]);

  if (!selectedLead) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-30 backdrop-blur-[2px]"
        onClick={closeDrawer}
      />

      {/* Drawer panel */}
      <div className="fixed right-0 top-0 h-full w-[480px] max-w-full bg-white border-l border-black/5 shadow-soft z-40 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/5 shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigateDrawer(-1)}
              disabled={!hasPrev}
              className="p-1.5 rounded-lg hover:bg-black/5 text-muted disabled:opacity-30 transition-colors"
              aria-label="Предыдущий"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              onClick={() => navigateDrawer(1)}
              disabled={!hasNext}
              className="p-1.5 rounded-lg hover:bg-black/5 text-muted disabled:opacity-30 transition-colors"
              aria-label="Следующий"
            >
              <ChevronRight size={16} />
            </button>
            <span className="font-mono text-[10px] text-muted-3">
              {currentIndex + 1} / {visibleLeads.length}
            </span>
          </div>
          <button
            onClick={closeDrawer}
            className="p-1.5 rounded-lg hover:bg-black/5 text-muted transition-colors"
            aria-label="Закрыть"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body — scrollable */}
        <div className="flex-1 overflow-y-auto">
          <DrawerBody lead={selectedLead} />
        </div>

        {/* Footer action */}
        <div className="px-6 py-4 border-t border-black/5 shrink-0">
          <Link
            href={`/leads/${selectedLead.id}`}
            className="flex items-center justify-center gap-2 w-full bg-ink text-white rounded-pill py-3 text-sm font-semibold transition-all duration-300 hover:bg-ink/90 active:scale-[0.98]"
          >
            Открыть полностью
            <ArrowRight size={15} />
          </Link>
        </div>
      </div>
    </>
  );
}

function DrawerBody({ lead }: { lead: LeadOut }) {
  return (
    <div className="px-6 py-5 space-y-6">
      {/* Company header */}
      <div>
        <h2 className="text-2xl font-extrabold tracking-tight text-ink leading-snug mb-1">
          {lead.company_name}
        </h2>
        {(lead.segment || lead.city) && (
          <p className="font-mono text-xs uppercase tracking-[0.1em] text-muted-2">
            {[lead.segment, lead.city].filter(Boolean).join(" · ")}
          </p>
        )}
      </div>

      {/* Meta badges */}
      <div className="flex flex-wrap gap-2">
        {lead.priority && (
          <Badge className={PRIORITY_COLORS[lead.priority] ?? "text-muted bg-black/5"}>
            Приоритет {lead.priority}
          </Badge>
        )}
        {lead.deal_type && (
          <Badge className="text-muted-2 bg-black/5">
            {DEAL_TYPE_LABELS[lead.deal_type] ?? lead.deal_type}
          </Badge>
        )}
        {lead.score > 0 && (
          <Badge className="text-muted-2 bg-black/5 font-mono">
            Score {lead.score}
          </Badge>
        )}
        {lead.fit_score != null && (
          <Badge className="text-accent bg-accent/10 font-mono">
            Fit {lead.fit_score}
          </Badge>
        )}
      </div>

      {/* AI Brief */}
      <Section title="AI Brief">
        {lead.ai_data ? (
          <AiBriefContent data={lead.ai_data} />
        ) : (
          <p className="text-sm text-muted-2 italic">
            AI Brief появится после enrichment
          </p>
        )}
      </Section>

      {/* Blocker */}
      {lead.blocker && (
        <Section title="Блокер">
          <div className="flex items-start gap-2 text-rose">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <p className="text-sm">{lead.blocker}</p>
          </div>
        </Section>
      )}

      {/* Next step */}
      {lead.next_step && (
        <Section title="Следующий шаг">
          <div className="flex items-start gap-2 text-success">
            <CheckCircle2 size={15} className="mt-0.5 shrink-0" />
            <p className="text-sm">{lead.next_step}</p>
          </div>
        </Section>
      )}

      {/* Rotting warnings */}
      {(lead.is_rotting_stage || lead.is_rotting_next_step) && (
        <div className="bg-warning/5 border border-warning/15 rounded-xl px-4 py-3">
          <p className="text-sm font-semibold text-warning mb-0.5">Карточка протухает</p>
          <p className="text-xs text-warning/80">
            {lead.is_rotting_stage && "Слишком долго в текущей стадии. "}
            {lead.is_rotting_next_step && "Следующий шаг просрочен."}
          </p>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 mb-2">
        {title}
      </p>
      {children}
    </div>
  );
}

function Badge({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`text-xs font-semibold px-2.5 py-1 rounded-pill ${className ?? ""}`}
    >
      {children}
    </span>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function AiBriefContent({ data }: { data: Record<string, any> }) {
  if (typeof data === "string") {
    return <p className="text-sm text-ink/80 leading-relaxed">{data}</p>;
  }
  if (data.summary) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-ink/80 leading-relaxed">{data.summary}</p>
        {data.pain_points && Array.isArray(data.pain_points) && (
          <div>
            <p className="text-xs font-semibold text-muted mb-1">Боли</p>
            <ul className="list-disc list-inside space-y-0.5">
              {(data.pain_points as string[]).map((p, i) => (
                <li key={i} className="text-sm text-muted-2">
                  {p}
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.opportunities && Array.isArray(data.opportunities) && (
          <div>
            <p className="text-xs font-semibold text-muted mb-1">Возможности</p>
            <ul className="list-disc list-inside space-y-0.5">
              {(data.opportunities as string[]).map((o, i) => (
                <li key={i} className="text-sm text-muted-2">
                  {o}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }
  // Fallback: render as JSON in a code block
  return (
    <pre className="text-xs font-mono bg-canvas rounded-lg p-3 overflow-x-auto text-muted whitespace-pre-wrap break-words">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
