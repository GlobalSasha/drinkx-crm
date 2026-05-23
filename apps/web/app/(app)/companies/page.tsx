"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Search } from "lucide-react";
import { useCompanies } from "@/lib/hooks/use-companies";
import type { CompanyOut } from "@/lib/types";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/Empty";

const columns: ColumnDef<CompanyOut, unknown>[] = [
  {
    accessorKey: "name",
    header: "Название",
    cell: (info) => (
      <span className="type-body text-brand-accent font-medium">
        {(info.getValue() as string) || "—"}
      </span>
    ),
  },
  {
    accessorKey: "city",
    header: "Город",
    cell: (info) => (
      <span className="type-caption text-brand-muted">
        {(info.getValue() as string | null) ?? "—"}
      </span>
    ),
  },
  {
    accessorKey: "primary_segment",
    header: "Сегмент",
    cell: (info) => (
      <span className="type-caption text-brand-muted">
        {(info.getValue() as string | null) ?? "—"}
      </span>
    ),
  },
  {
    accessorKey: "inn",
    header: "ИНН",
    cell: (info) => (
      <span className="type-caption font-mono text-brand-muted">
        {(info.getValue() as string | null) ?? "—"}
      </span>
    ),
  },
];

export default function CompaniesPage() {
  const [search, setSearch] = useState("");
  const router = useRouter();

  // The hook accepts filter params; we use city/segment/archived but not a text
  // search param — filter client-side on name/inn/city for simplicity.
  const { data, isLoading } = useCompanies();
  const allRows: CompanyOut[] = (data?.items ?? []).filter((c) => !c.is_archived);

  const rows = search.trim()
    ? allRows.filter((c) => {
        const q = search.trim().toLowerCase();
        return (
          c.name.toLowerCase().includes(q) ||
          (c.inn ?? "").toLowerCase().includes(q) ||
          (c.city ?? "").toLowerCase().includes(q)
        );
      })
    : allRows;

  return (
    <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
      <div className="flex items-center gap-2 mb-5">
        <Building2 size={22} className="text-brand-accent" />
        <h1 className="type-page-title text-brand-primary">Компании</h1>
      </div>

      <div className="mb-4 relative max-w-md">
        <Search
          size={13}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted pointer-events-none"
        />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по названию, ИНН, городу"
          className="w-full pl-8 pr-3 py-2 type-caption bg-white border border-brand-border rounded-full outline-none focus:border-brand-accent"
        />
      </div>

      {isLoading && rows.length === 0 ? (
        <p className="type-caption text-brand-muted py-6 text-center">Загрузка…</p>
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          rowKey={(r) => r.id}
          rowLabel={(r) => `Открыть карточку: ${r.name}`}
          onRowClick={(r) => {
            router.push(`/companies/${r.id}` as never);
          }}
          emptyState={
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Building2 />
                </EmptyMedia>
                <EmptyTitle>{search ? "Ничего не найдено" : "Компаний пока нет"}</EmptyTitle>
                <EmptyDescription>
                  {search
                    ? "Попробуйте другой запрос или очистите поиск."
                    : "Компании появятся здесь автоматически по мере появления лидов."}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          }
        />
      )}
    </main>
  );
}
