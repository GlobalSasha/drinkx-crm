"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { History, ChevronLeft, ChevronRight, AlertCircle } from "lucide-react";
import { useMe } from "@/lib/hooks/use-me";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useAuditLog } from "@/lib/hooks/use-audit";
import { relativeTime } from "@/lib/relative-time";
import { T } from "@/lib/design-system";
import type { AuditLogOut } from "@/lib/types";

const PAGE_SIZE = 50;

const ACTION_FILTERS: { value: string | null; label: string }[] = [
  { value: null, label: "Все" },
  { value: "lead.create", label: "Создан лид" },
  { value: "lead.transfer", label: "Передан лид" },
  { value: "lead.move_stage", label: "Смена стадии" },
  { value: "enrichment.trigger", label: "Запрошен AI Brief" },
];

function shortId(id: string | null): string {
  if (!id) return "—";
  return id.slice(0, 8);
}

/**
 * Render a delta payload for the «Изменения» column.
 *
 * Specific actions get a friendly inline format — for everyone else
 * we fall back to a truncated JSON dump. Truncation budget = 80 chars
 * so single-row scanning stays comfortable in the audit page table.
 */
function formatDelta(
  action: string,
  delta: Record<string, unknown> | null,
): string {
  if (!delta) return "—";
  const get = (key: string): string | null => {
    const v = delta[key];
    return typeof v === "string" ? v : null;
  };
  switch (action) {
    case "lead.move_stage": {
      const from = get("from_stage");
      const to = get("to_stage");
      if (from && to) return `${from} → ${to}`;
      break;
    }
    case "lead.transfer": {
      const from = get("from_user");
      const to = get("to_user");
      if (from && to) return `${from} → ${to}`;
      break;
    }
    case "lead.create": {
      const name = get("name") ?? get("company_name");
      if (name) return name;
      break;
    }
    case "template.create":
    case "template.update": {
      const name = get("name");
      if (name) return name;
      break;
    }
  }
  // Generic JSON-dump fallback. Same behavior as the pre-G5 default,
  // just used for actions that don't have a tailored renderer.
  try {
    const s = JSON.stringify(delta);
    return s.length > 80 ? s.slice(0, 80) + "…" : s;
  } catch {
    return "—";
  }
}

function SkeletonRow() {
  return (
    <tr className="animate-pulse border-b border-brand-border">
      <td className="px-4 py-3"><div className="h-3 w-16 bg-black/5 rounded" /></td>
      <td className="px-4 py-3"><div className="h-3 w-28 bg-black/5 rounded" /></td>
      <td className="px-4 py-3"><div className="h-3 w-24 bg-black/5 rounded" /></td>
      <td className="px-4 py-3"><div className="h-3 w-20 bg-black/5 rounded" /></td>
      <td className="px-4 py-3"><div className="h-3 w-48 bg-black/5 rounded" /></td>
    </tr>
  );
}

function AuditRow({ row }: { row: AuditLogOut }) {
  return (
    <tr className="border-b border-brand-border hover:bg-brand-bg/50 transition-colors">
      <td className="px-4 py-3 align-top">
        <span className={`${T.mono} text-brand-muted whitespace-nowrap`}>
          {relativeTime(row.created_at)}
        </span>
      </td>
      <td className="px-4 py-3 align-top">
        <span className={`${T.mono} font-semibold text-brand-primary bg-black/5 px-2 py-0.5 rounded-md whitespace-nowrap`}>
          {row.action}
        </span>
      </td>
      <td className="px-4 py-3 align-top">
        <span className={`${T.mono} text-brand-muted`}>
          {row.entity_type || "—"}
          {row.entity_id && (
            <>
              {" · "}
              <span className="text-brand-muted">{shortId(row.entity_id)}</span>
            </>
          )}
        </span>
      </td>
      <td className="px-4 py-3 align-top max-w-[200px]">
        {row.user_full_name && row.user_email ? (
          <span className="text-xs text-brand-primary truncate block">
            <span
              className="font-semibold"
              title={row.user_email}
            >
              {row.user_full_name}
            </span>
            <span className={`text-brand-muted ${T.mono}`}> · {row.user_email}</span>
          </span>
        ) : (
          <span
            className={`${T.mono} text-brand-muted`}
            title={row.user_id ?? "system"}
          >
            {shortId(row.user_id)}
          </span>
        )}
      </td>
      <td className="px-4 py-3 align-top max-w-[480px]">
        <span
          className={`${T.mono} text-brand-muted break-all`}
          title={row.delta_json ? JSON.stringify(row.delta_json) : ""}
        >
          {formatDelta(row.action, row.delta_json)}
        </span>
      </td>
    </tr>
  );
}

export default function AuditPage() {
  const router = useRouter();
  const { data: me, isLoading: meLoading } = useMe();
  const [actionFilter, setActionFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // Reset to page 1 whenever the filter changes — otherwise we may land on
  // an out-of-range page for the new filter and see an empty table.
  useEffect(() => {
    setPage(1);
  }, [actionFilter]);

  // Admin-only route guard. Redirect non-admins to /today.
  // We wait for `me` to resolve — without that, role==undefined would briefly
  // bounce admins out before the hook fills in their role.
  useEffect(() => {
    if (meLoading) return;
    if (!me) return;
    if (me.role !== "admin") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      router.replace("/today" as any);
    }
  }, [meLoading, me, router]);

  // Filter is currently action-based (the spec calls it that way), but the
  // backend filter is `entity_type`. Two of the listed actions share
  // entity_type="lead", so action-based filtering needs the action field
  // too. The backend currently exposes only entity_type/entity_id — we ask
  // for entity_type="lead" when a lead.* filter is selected, then
  // additionally narrow client-side by action. enrichment.trigger lives on
  // entity_type="lead" too, so the same path applies.
  const isLeadAction = actionFilter?.startsWith("lead.") ?? false;
  const isEnrichment = actionFilter === "enrichment.trigger";
  const queryEntityType =
    isLeadAction || isEnrichment ? "lead" : undefined;

  const { data, isLoading, isError, refetch, isFetching } = useAuditLog({
    entity_type: queryEntityType,
    page,
  });

  const allItems = data?.items ?? [];
  const filteredItems = actionFilter
    ? allItems.filter((r) => r.action === actionFilter)
    : allItems;

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // Don't render content for non-admins (the redirect effect will fire).
  if (!meLoading && me && me.role !== "admin") {
    return null;
  }

  return (
    <div className={pageContainerVariants({ surface: "data" })}>
      <PageHeader
        icon={<History size={20} />}
        title="Журнал изменений"
        subtitle="Только для администраторов · все записи в этом workspace"
        actions={
          <div className={`${T.mono} text-brand-muted tabular-nums`}>
            {total > 0 ? `${total} записей` : ""}
          </div>
        }
      />

      {/* Filter chips */}
      <div className="flex flex-wrap items-center gap-1.5 mb-4">
        {ACTION_FILTERS.map((f) => {
          const isActive = actionFilter === f.value;
          return (
            <button
              key={f.label}
              onClick={() => setActionFilter(f.value)}
              className={`${T.mono} px-3 py-1.5 rounded-full transition-colors ${
                isActive
                  ? "bg-brand-accent text-white font-semibold"
                  : "bg-brand-panel text-brand-muted hover:bg-brand-border hover:text-brand-primary"
              }`}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="bg-white border border-brand-border rounded-card overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-brand-bg/60">
            <tr className="border-b border-brand-border">
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-brand-muted font-semibold w-[110px]`}>
                Время
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-brand-muted font-semibold w-[180px]`}>
                Действие
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-brand-muted font-semibold w-[160px]`}>
                Сущность
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-brand-muted font-semibold w-[120px]`}>
                Пользователь
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-brand-muted font-semibold`}>
                Изменения
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading && Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}

            {!isLoading && isError && (
              <tr>
                <td colSpan={5} className="px-4 py-12">
                  <div className="flex flex-col items-center text-center gap-3">
                    <AlertCircle size={20} className="text-rose" />
                    <p className="text-sm text-rose font-semibold">
                      Не удалось загрузить журнал
                    </p>
                    <button
                      onClick={() => refetch()}
                      disabled={isFetching}
                      className="text-xs font-semibold text-brand-accent hover:text-brand-accent/80 transition-colors disabled:opacity-50"
                    >
                      Повторить
                    </button>
                  </div>
                </td>
              </tr>
            )}

            {!isLoading && !isError && filteredItems.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-16 text-center">
                  <p className="text-sm text-brand-muted">Событий пока нет</p>
                </td>
              </tr>
            )}

            {!isLoading && !isError &&
              filteredItems.map((row) => <AuditRow key={row.id} row={row} />)}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="inline-flex items-center gap-1 text-xs font-semibold text-brand-muted hover:text-brand-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft size={14} />
            Назад
          </button>
          <span className={`${T.mono} text-brand-muted tabular-nums`}>
            Страница {page} из {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="inline-flex items-center gap-1 text-xs font-semibold text-brand-muted hover:text-brand-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Вперёд
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
