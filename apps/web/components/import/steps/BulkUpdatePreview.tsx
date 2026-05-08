"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { clsx } from "clsx";

import { useApplyImport } from "@/lib/hooks/use-import";
import { ApiError } from "@/lib/api-client";
import type {
  BulkUpdateChange,
  BulkUpdateDiffItem,
  ImportJobOut,
} from "@/lib/types";

const VISIBLE_ITEMS = 20;

interface Props {
  job: ImportJobOut;
  onClose: () => void;
  onApplied: (job: ImportJobOut) => void;
}

export function BulkUpdatePreview({ job, onClose, onApplied }: Props) {
  const diff = job.diff_json ?? {};
  const items: BulkUpdateDiffItem[] = (diff.items ?? []) as BulkUpdateDiffItem[];
  const stats = diff.stats ?? { to_update: 0, to_create: 0, errors: 0 };

  const [error, setError] = useState<string | null>(null);
  const apply = useApplyImport();

  // Split for the rendered list — actionable items first, errors below
  // in their own section so the manager can scan them separately.
  const actionable = useMemo(
    () => items.filter((i) => !i.error),
    [items],
  );
  const failed = useMemo(() => items.filter((i) => !!i.error), [items]);

  function startApply() {
    setError(null);
    apply.mutate(job.id, {
      onSuccess: onApplied,
      onError: (err) => {
        const detail =
          err instanceof ApiError && typeof err.body === "object" && err.body
            ? (err.body as { detail?: unknown }).detail
            : null;
        setError(detail ? String(detail) : "Не удалось запустить применение");
      },
    });
  }

  const totalActionable = stats.to_update + stats.to_create;

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-2">
        <div className="w-8 h-8 rounded-xl bg-accent/10 text-accent flex items-center justify-center shrink-0">
          <Sparkles size={16} />
        </div>
        <div>
          <h3 className="text-base font-extrabold tracking-tight text-ink">
            Изменения от AI
          </h3>
          <p className="text-[13px] text-muted mt-1">
            Проверьте предложенные обновления. Применяются в фоне; неизменные
            лиды AI исключил из ответа.
          </p>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <StatCard
          tone="info"
          icon={<RefreshCw size={16} />}
          label="Обновить"
          value={stats.to_update}
          unit={pluralKartochek(stats.to_update)}
        />
        <StatCard
          tone="success"
          icon={<Plus size={16} />}
          label="Создать"
          value={stats.to_create}
          unit={pluralKartochek(stats.to_create)}
        />
        <StatCard
          tone={stats.errors > 0 ? "warning" : "neutral"}
          icon={<AlertTriangle size={16} />}
          label="Ошибки"
          value={stats.errors}
          unit="записей"
        />
      </div>

      {/* Actionable items list */}
      {actionable.length > 0 && (
        <div className="rounded-2xl border border-black/5 bg-white">
          <div className="px-4 py-2.5 bg-canvas border-b border-black/5 text-[10px] font-mono uppercase tracking-wider text-muted-2">
            Изменения{" "}
            <span className="text-muted-3 ml-1">
              {actionable.length > VISIBLE_ITEMS
                ? `первые ${VISIBLE_ITEMS} из ${actionable.length}`
                : actionable.length}
            </span>
          </div>
          <div className="divide-y divide-black/5 max-h-[44vh] overflow-y-auto">
            {actionable.slice(0, VISIBLE_ITEMS).map((item, i) => (
              <DiffRow key={`${item.lead_id ?? "new"}-${i}`} item={item} />
            ))}
          </div>
        </div>
      )}

      {/* Errors panel */}
      {failed.length > 0 && (
        <div className="rounded-2xl border border-amber-200/60 bg-amber-50">
          <div className="px-4 py-2.5 border-b border-amber-200/60 flex items-center gap-1.5 text-[11px] font-bold text-amber-800">
            <AlertTriangle size={13} />
            Не удалось распознать
            <span className="font-mono ml-1">{failed.length}</span>
          </div>
          <div className="divide-y divide-amber-200/40 max-h-[24vh] overflow-y-auto">
            {failed.slice(0, VISIBLE_ITEMS).map((item, i) => (
              <div
                key={`err-${i}`}
                className="px-4 py-2.5 text-[12px] flex items-baseline gap-2"
              >
                <span className="font-semibold text-ink">
                  {item.company_name || "—"}
                </span>
                <span className="text-amber-800 truncate">{item.error}</span>
              </div>
            ))}
            {failed.length > VISIBLE_ITEMS && (
              <div className="px-4 py-2 text-[11px] font-mono text-amber-800/70">
                …и ещё {failed.length - VISIBLE_ITEMS}
              </div>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="text-[13px] text-red-700 bg-red-50 rounded-xl px-3 py-2.5">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <button
          onClick={onClose}
          disabled={apply.isPending}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
        >
          <ChevronLeft size={14} />
          Отмена
        </button>
        <button
          onClick={startApply}
          disabled={totalActionable === 0 || apply.isPending}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-pill bg-accent text-white text-sm font-semibold hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-300"
        >
          {apply.isPending && <Loader2 size={14} className="animate-spin" />}
          {apply.isPending
            ? "Применяем…"
            : totalActionable === 0
              ? "Нет изменений"
              : "Применить изменения"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-item row (collapsible)
// ---------------------------------------------------------------------------

function DiffRow({ item }: { item: BulkUpdateDiffItem }) {
  const [open, setOpen] = useState(false);
  const isCreate = item.action === "create";
  const summary = useMemo(() => summariseChanges(item.changes), [item.changes]);

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-4 py-3 flex items-start gap-3 text-left hover:bg-canvas/50 transition-colors"
      >
        <ChevronRight
          size={14}
          className={clsx(
            "mt-0.5 shrink-0 text-muted-3 transition-transform",
            open && "rotate-90",
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-sm font-bold text-ink truncate">
              {item.company_name || "—"}
            </span>
            <ActionBadge isCreate={isCreate} />
            {item.inn && (
              <span className="font-mono text-[10px] text-muted-3">
                ИНН {item.inn}
              </span>
            )}
          </div>
          {summary && (
            <div className="text-[12px] text-muted-2 mt-0.5 truncate">
              {summary}
            </div>
          )}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-3 -mt-1">
          <div className="rounded-xl bg-canvas/60 px-3 py-2 space-y-1">
            {item.changes.length === 0 && (
              <div className="text-[12px] text-muted-3">
                Полей для изменения нет.
              </div>
            )}
            {item.changes.map((c, i) => (
              <ChangeLine key={i} change={c} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ActionBadge({ isCreate }: { isCreate: boolean }) {
  return (
    <span
      className={clsx(
        "text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-md",
        isCreate
          ? "bg-emerald-500/10 text-emerald-700"
          : "bg-blue-500/10 text-blue-700",
      )}
    >
      {isCreate ? "create" : "update"}
    </span>
  );
}

function ChangeLine({ change }: { change: BulkUpdateChange }) {
  const sign = OP_SIGN[change.op] ?? "·";
  const tone = OP_TONE[change.op] ?? "text-muted-2";
  return (
    <div className="flex items-baseline gap-2 text-[12px]">
      <span className={clsx("font-mono shrink-0 w-3 text-center", tone)}>
        {sign}
      </span>
      <span className="font-mono text-[10px] text-muted-3 shrink-0">
        {change.field}
      </span>
      <span className="text-ink truncate">{formatValue(change)}</span>
    </div>
  );
}

const OP_SIGN: Record<BulkUpdateChange["op"], string> = {
  add: "+",
  remove: "−",
  replace: "↻",
  set: "~",
};

const OP_TONE: Record<BulkUpdateChange["op"], string> = {
  add: "text-emerald-600",
  remove: "text-rose-600",
  replace: "text-amber-600",
  set: "text-muted",
};

function formatValue(c: BulkUpdateChange): string {
  // Scalar set with previous value → render «X → Y» so the manager
  // sees what changed at a glance.
  if (c.op === "set" && c.current_value !== null && c.current_value !== undefined) {
    return `${formatScalar(c.current_value)} → ${formatScalar(c.value)}`;
  }
  return formatScalar(c.value);
}

function formatScalar(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) {
    if (v.length === 0) return "[]";
    return v
      .map((x) =>
        typeof x === "object" && x !== null
          ? (x as { name?: string; email?: string }).name ??
            (x as { email?: string }).email ??
            JSON.stringify(x)
          : String(x),
      )
      .join(", ");
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function summariseChanges(changes: BulkUpdateChange[]): string {
  if (!changes.length) return "Без полевых изменений";
  const buckets = new Map<string, number>();
  for (const c of changes) {
    const top = c.field.split(".")[0];
    buckets.set(top, (buckets.get(top) ?? 0) + 1);
  }
  return Array.from(buckets.entries())
    .map(([k, n]) => `${k}${n > 1 ? `×${n}` : ""}`)
    .join(" · ");
}

function pluralKartochek(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return "карточек";
  if (mod10 === 1) return "карточка";
  if (mod10 >= 2 && mod10 <= 4) return "карточки";
  return "карточек";
}

function StatCard({
  tone,
  icon,
  label,
  value,
  unit,
}: {
  tone: "success" | "warning" | "info" | "neutral";
  icon: React.ReactNode;
  label: string;
  value: number;
  unit: string;
}) {
  const palette = {
    info: "bg-blue-50 text-blue-700 border-blue-200/60",
    success: "bg-emerald-50 text-emerald-700 border-emerald-200/60",
    warning: "bg-amber-50 text-amber-800 border-amber-200/60",
    neutral: "bg-canvas text-ink border-black/5",
  }[tone];
  return (
    <div
      className={`rounded-2xl border ${palette} px-4 py-3.5 flex flex-col gap-1.5`}
    >
      <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider opacity-80">
        {icon}
        {label}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-3xl font-extrabold tracking-tight tabular-nums">
          {value}
        </span>
        <span className="text-[11px] opacity-70">{unit}</span>
      </div>
    </div>
  );
}
