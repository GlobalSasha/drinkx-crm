"use client";
import type { LeadOut, FeedItemOut } from "@/lib/types";
import { C } from "@/lib/design-system";
import { Badge, type BadgeProps } from "@/components/ui/Badge";
import { NextStepBanner } from "./feed/NextStepBanner";
import { LeadInfoBlock } from "./LeadInfoBlock";
import { PrimaryContactCard } from "./PrimaryContactCard";
import { SourceSection } from "./SourceSection";
import { CustomFieldsPanel } from "./CustomFieldsPanel";

// Always-visible left column of the lead card. Independent of the right
// column's active tab. Order is act-now → details: summary, next step,
// deal params, primary contact, source, custom fields.

function formatRub(value: number | string | null | undefined): string {
  if (value == null || value === "") return "Не указана";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "Не указана";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) + " ₽";
}

const PRIORITY_VARIANT: Record<string, BadgeProps["variant"]> = {
  A: "success",
  B: "success2",
  C: "warning",
  D: "neutral",
};

export function LeadLeftColumn({
  lead,
  items,
  onCreateTaskRequest,
  onOpenTab,
}: {
  lead: LeadOut;
  items: FeedItemOut[];
  onCreateTaskRequest: () => void;
  onOpenTab?: (tab: string) => void;
}) {
  return (
    <div className="space-y-4">
      {/* Summary — money + priority at a glance */}
      <div className="rounded-card border border-brand-border bg-white p-4">
        {lead.priority && (
          <Badge variant={PRIORITY_VARIANT[lead.priority] ?? "neutral"}>
            Приоритет {lead.priority}
          </Badge>
        )}
        <p className={`type-hint text-brand-muted ${lead.priority ? "mt-2.5" : ""}`}>
          Сумма сделки
        </p>
        <p className={`type-card-title ${C.color.text} tabular-nums`}>{formatRub(lead.deal_amount)}</p>
      </div>

      {/* Next step — nearest open task / «поставить задачу» */}
      <NextStepBanner items={items} onCreateTaskRequest={onCreateTaskRequest} />

      {/* Deal params (inline-editable) */}
      <LeadInfoBlock lead={lead} />

      {/* Primary contact */}
      <PrimaryContactCard
        lead={lead}
        onOpenContacts={onOpenTab ? () => onOpenTab("contacts") : undefined}
      />

      {/* Source (renders only for form-sourced leads) */}
      <SourceSection lead={lead} />

      {/* Custom fields (renders only when the workspace has any) */}
      <CustomFieldsPanel leadId={lead.id} />
    </div>
  );
}
