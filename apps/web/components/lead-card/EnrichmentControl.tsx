"use client";

import { Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api-client";
import { useLatestEnrichment, useTriggerEnrichment } from "@/lib/hooks/use-enrichment";

function triggerError(error: ApiError): string {
  const detail = (error.body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (error.status === 409) return "Обогащение уже запущено. Обновите статус.";
  return "Не удалось запустить AI. Повторите попытку позже.";
}

export function EnrichmentControl({ leadId }: { leadId: string }) {
  const latest = useLatestEnrichment(leadId);
  const trigger = useTriggerEnrichment(leadId);
  const running = trigger.isPending || latest.data?.status === "running";

  return (
    <div className="mb-4 flex flex-col items-start gap-2">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="max-w-full whitespace-normal text-left"
        disabled={running || latest.isPending || latest.isError}
        onClick={() => trigger.mutate("append")}
      >
        {running ? <Loader2 size={16} className="shrink-0 animate-spin" /> : <Sparkles size={16} className="shrink-0" />}
        {running ? "AI ищет сведения…" : "Дополнить через AI"}
      </Button>
      <p className="text-xs text-brand-muted" role="status" aria-live="polite">
        {running
          ? "Можно продолжать работу — карточка обновится автоматически."
          : latest.data?.status === "succeeded"
            ? "Обогащение завершено. Заполненные сведения сохранены."
            : "Дополнит описание и контакты, сохранив заполненные сведения."}
      </p>
      {trigger.error && <p role="alert" className="text-xs text-rose">{triggerError(trigger.error)}</p>}
      {!running && latest.data?.status === "failed" && (
        <p role="alert" className="text-xs text-rose">AI не смог дополнить карточку. Прежние сведения сохранены; можно повторить запуск.</p>
      )}
      {latest.isError && (
        <p role="alert" className="text-xs text-rose">
          Не удалось проверить статус AI.{" "}
          <button type="button" className="underline" onClick={() => void latest.refetch()}>Обновить статус</button>
        </p>
      )}
    </div>
  );
}
