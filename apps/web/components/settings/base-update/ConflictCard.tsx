"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import type {
  IngestConflictOut,
  IngestConflictResolution,
} from "@/lib/types";
import { useResolveConflict } from "@/lib/hooks/use-base-update";

interface Props {
  jobId: string;
  conflict: IngestConflictOut;
}

const TYPE_LABEL: Record<string, string> = {
  company_ambiguous: "Похожих компаний в базе",
  field_mismatch: "Поле расходится",
  contact_mismatch: "Контакт расходится",
  lead_target: "Выбор лида",
  low_confidence: "Низкая уверенность извлечения",
  batch_duplicate: "Дубль в пачке",
};

export function ConflictCard({ jobId, conflict }: Props) {
  const resolve = useResolveConflict(jobId);
  const [picked, setPicked] = useState<string>("");
  const [manualValue, setManualValue] = useState<string>("");

  const isResolved = conflict.status !== "open";

  function submit(resolution: IngestConflictResolution, resolvedValue?: string) {
    resolve.mutate({
      conflictId: conflict.id,
      body: { resolution, resolved_value: resolvedValue ?? null },
    });
  }

  const buttons = renderButtons(conflict, {
    submit,
    picked,
    setPicked,
    manualValue,
    setManualValue,
    pending: resolve.isPending,
  });

  return (
    <div className="bg-white border border-brand-border rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="type-caption text-brand-muted">
          {TYPE_LABEL[conflict.type] ?? conflict.type}
          {conflict.field_name && (
            <span className="text-brand-primary"> · {conflict.field_name}</span>
          )}
        </div>
        {isResolved && (
          <span className="type-caption text-success">
            ✓ решено{conflict.resolution ? ` (${conflict.resolution})` : ""}
          </span>
        )}
      </div>

      {(conflict.base_value !== null || conflict.incoming_value !== null) && (
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <div className="type-caption text-brand-muted mb-1">В базе</div>
            <div className="type-body text-brand-primary break-words">
              {conflict.base_value ?? "—"}
            </div>
          </div>
          <div>
            <div className="type-caption text-brand-muted mb-1">Из карточки</div>
            <div className="type-body text-brand-primary break-words">
              {conflict.incoming_value ?? "—"}
            </div>
          </div>
        </div>
      )}

      {conflict.candidates_json && conflict.candidates_json.length > 0 && (
        <div className="type-caption text-brand-muted">
          Кандидаты: {conflict.candidates_json.map((c) => c.name).join(" · ")}
        </div>
      )}

      {!isResolved && (
        <div className="flex flex-wrap gap-2 pt-1">{buttons}</div>
      )}
    </div>
  );
}

function renderButtons(
  conflict: IngestConflictOut,
  ctx: {
    submit: (r: IngestConflictResolution, v?: string) => void;
    picked: string;
    setPicked: (v: string) => void;
    manualValue: string;
    setManualValue: (v: string) => void;
    pending: boolean;
  },
) {
  const { submit, picked, setPicked, manualValue, setManualValue, pending } = ctx;
  const btn = "px-3 py-1.5 rounded-full type-caption font-semibold transition-colors";
  const primary = `${btn} bg-brand-accent text-white hover:bg-brand-accent/90`;
  const ghost = `${btn} bg-brand-bg text-brand-primary hover:bg-brand-panel`;
  const danger = `${btn} bg-rose/10 text-rose hover:bg-rose/15`;
  const disabled = "opacity-40 pointer-events-none";

  if (conflict.type === "field_mismatch") {
    return (
      <>
        <button className={`${ghost} ${pending ? disabled : ""}`} onClick={() => submit("keep")}>
          Оставить базу
        </button>
        <button className={`${primary} ${pending ? disabled : ""}`} onClick={() => submit("overwrite")}>
          Взять из карточки
        </button>
        <input
          value={manualValue}
          onChange={(e) => setManualValue(e.target.value)}
          placeholder="Ввести вручную…"
          className="px-3 py-1.5 rounded-full bg-brand-bg type-caption outline-none border border-transparent focus:border-brand-accent w-48"
        />
        <button
          className={`${primary} ${!manualValue.trim() || pending ? disabled : ""}`}
          onClick={() => submit("manual", manualValue.trim())}
        >
          Сохранить вручную
        </button>
        {pending && <Loader2 size={14} className="animate-spin text-brand-muted self-center" />}
      </>
    );
  }

  if (conflict.type === "company_ambiguous") {
    const candidates = conflict.candidates_json ?? [];
    return (
      <>
        <select
          value={picked}
          onChange={(e) => setPicked(e.target.value)}
          className="px-3 py-1.5 rounded-full bg-brand-bg type-caption outline-none border border-transparent focus:border-brand-accent"
        >
          <option value="">— выбрать компанию —</option>
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <button
          className={`${primary} ${!picked || pending ? disabled : ""}`}
          onClick={() => submit("pick", picked)}
        >
          Выбрать
        </button>
        <button className={`${ghost} ${pending ? disabled : ""}`} onClick={() => submit("keep")}>
          Создать новую
        </button>
        <button className={`${danger} ${pending ? disabled : ""}`} onClick={() => submit("skip")}>
          Пропустить
        </button>
      </>
    );
  }

  if (conflict.type === "low_confidence") {
    return (
      <>
        <input
          value={manualValue}
          onChange={(e) => setManualValue(e.target.value)}
          placeholder="Заметка / корректировка"
          className="px-3 py-1.5 rounded-full bg-brand-bg type-caption outline-none border border-transparent focus:border-brand-accent w-64"
        />
        <button
          className={`${primary} ${pending ? disabled : ""}`}
          onClick={() => submit("manual", manualValue.trim() || undefined)}
        >
          Сохранить вручную
        </button>
        <button className={`${danger} ${pending ? disabled : ""}`} onClick={() => submit("skip")}>
          Пропустить
        </button>
      </>
    );
  }

  if (conflict.type === "batch_duplicate") {
    return (
      <>
        <button className={`${primary} ${pending ? disabled : ""}`} onClick={() => submit("keep")}>
          Подтвердить слияние
        </button>
        <button className={`${ghost} ${pending ? disabled : ""}`} onClick={() => submit("add_separate")}>
          Это разные компании
        </button>
      </>
    );
  }

  // contact_mismatch + lead_target — backend dispatch deferred to a follow-up.
  // Admin can still mark them resolved (skip) to clear the job; the actual
  // write will land in the next iteration.
  return (
    <>
      <span className="type-caption text-brand-muted italic">
        Обработка перенесена в следующую итерацию — можно пропустить.
      </span>
      <button className={`${ghost} ${pending ? disabled : ""}`} onClick={() => submit("skip")}>
        Пропустить
      </button>
    </>
  );
}
