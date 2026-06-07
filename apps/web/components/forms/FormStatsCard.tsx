"use client";

// Sprint 3.6 G8 — per-form stats strip rendered under each row of the
// /forms admin page. Calls `useFormStats(formId)` (staleTime 60s) and
// surfaces «X за 7д · Y за 30д · Z в работе · Q% квалификация+».

import { Loader2 } from "lucide-react";
import { useFormStats } from "@/lib/hooks/use-forms";

interface Props {
  formId: string;
}

export function FormStatsCard({ formId }: Props) {
  const { data, isLoading, isError } = useFormStats(formId);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 mt-2 text-xs text-brand-muted">
        <Loader2 size={11} className="animate-spin" />
        Загружаем статистику…
      </div>
    );
  }
  if (isError || !data) {
    return null; // silent — admin doesn't need an error toast per row
  }

  const total = data.submissions_30d;
  // «квалификация+» = доля заявок, продвинувшихся хотя бы на одну
  // стадию дальше «Новый контакт» / «Без этапа». Both names protected
  // against in case stage labels differ across workspaces.
  const firstStageCount =
    (data.by_stage["Новый контакт"] ?? 0) + (data.by_stage["Без этапа"] ?? 0);
  const past_first =
    total === 0
      ? 0
      : Math.round(((total - firstStageCount) / total) * 100);

  return (
    <div className="mt-2 flex items-center gap-3 flex-wrap text-xs font-mono text-brand-muted">
      <Stat label="за 7 дней" value={data.submissions_7d} />
      <Stat label="за 30 дней" value={data.submissions_30d} />
      <Stat label="в работе" value={data.claimed_count} />
      {total > 0 && <Stat label="квалификация+" value={`${past_first}%`} />}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <span>
      <span className="text-brand-primary font-semibold tabular-nums">{value}</span>{" "}
      <span className="opacity-70">{label}</span>
    </span>
  );
}
