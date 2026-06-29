"use client";

// Lead-source dictionary management (Sprint CEO G3). Admin/head curate the
// list of «откуда появился лид» picked in the lead-create form and grouped on
// the CEO overview. Read is open; writes are gated server-side (admin/head)
// and hidden here for other roles. System rows (Яндекс Директ, Сайт) can be
// renamed/toggled but not deleted.

import { useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";

import {
  useLeadSources,
  useCreateLeadSource,
  useUpdateLeadSource,
  useDeleteLeadSource,
} from "@/lib/hooks/use-lead-sources";
import { useMe } from "@/lib/hooks/use-me";
import type { LeadSource } from "@/lib/types";
import { C } from "@/lib/design-system";

export function LeadSourcesSection() {
  const { data: sources = [], isLoading } = useLeadSources(false);
  const me = useMe().data;
  const canEdit = me?.role === "admin" || me?.role === "head";

  const create = useCreateLeadSource();
  const [newName, setNewName] = useState("");
  const [newPaid, setNewPaid] = useState(false);

  function addSource() {
    const name = newName.trim();
    if (!name) return;
    create.mutate(
      { name, is_paid: newPaid, sort_order: (sources.length + 1) * 10 },
      {
        onSuccess: () => {
          setNewName("");
          setNewPaid(false);
        },
      },
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-bold text-brand-primary">Источники лидов</h2>
        <p className="type-caption text-brand-muted mt-1">
          Откуда появился лид — список выбирается при создании лида и группирует
          сводку руководителя. Отметь «платный» для рекламных каналов.
        </p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 size={18} className="animate-spin text-brand-muted" />
        </div>
      ) : (
        <ul className="space-y-2">
          {sources.map((s) => (
            <SourceRow key={s.id} source={s} canEdit={canEdit} />
          ))}
        </ul>
      )}

      {canEdit && (
        <div className="flex flex-wrap items-center gap-2 rounded-card border border-brand-border bg-white p-3">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Название источника"
            className="flex-1 min-w-[10rem] type-body bg-brand-bg border border-brand-border rounded-lg px-2 py-1.5 outline-none focus:border-brand-accent"
          />
          <label className="inline-flex items-center gap-1.5 type-caption text-brand-muted select-none">
            <input
              type="checkbox"
              checked={newPaid}
              onChange={(e) => setNewPaid(e.target.checked)}
              className="accent-brand-accent"
            />
            платный
          </label>
          <button
            type="button"
            onClick={addSource}
            disabled={create.isPending || !newName.trim()}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-caption font-semibold ${C.button.ghost} disabled:opacity-50`}
          >
            <Plus size={13} />
            Добавить
          </button>
        </div>
      )}
    </div>
  );
}

function SourceRow({ source, canEdit }: { source: LeadSource; canEdit: boolean }) {
  const update = useUpdateLeadSource();
  const del = useDeleteLeadSource();
  const [name, setName] = useState(source.name);

  function saveName() {
    const v = name.trim();
    if (v && v !== source.name) update.mutate({ id: source.id, patch: { name: v } });
  }

  return (
    <li className="flex flex-wrap items-center gap-2 rounded-card border border-brand-border bg-white px-3 py-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={saveName}
        disabled={!canEdit}
        className="flex-1 min-w-[10rem] type-body bg-transparent border border-transparent hover:border-brand-border rounded-lg px-2 py-1 outline-none focus:border-brand-accent disabled:opacity-70"
      />
      <label className="inline-flex items-center gap-1.5 type-caption text-brand-muted select-none">
        <input
          type="checkbox"
          checked={source.is_paid}
          disabled={!canEdit}
          onChange={(e) => update.mutate({ id: source.id, patch: { is_paid: e.target.checked } })}
          className="accent-brand-accent"
        />
        платный
      </label>
      <label className="inline-flex items-center gap-1.5 type-caption text-brand-muted select-none">
        <input
          type="checkbox"
          checked={source.is_active}
          disabled={!canEdit}
          onChange={(e) => update.mutate({ id: source.id, patch: { is_active: e.target.checked } })}
          className="accent-brand-accent"
        />
        активен
      </label>
      {source.is_system ? (
        <span className="ml-auto type-caption text-brand-muted font-mono text-2xs uppercase tracking-[0.12em]">
          системный
        </span>
      ) : (
        canEdit && (
          <button
            type="button"
            onClick={() => del.mutate(source.id)}
            disabled={del.isPending}
            aria-label="Удалить источник"
            className="ml-auto p-1.5 text-brand-muted hover:text-rose transition-colors disabled:opacity-50"
          >
            <Trash2 size={14} />
          </button>
        )
      )}
    </li>
  );
}
