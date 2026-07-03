"use client";
// /automations — Sprint 2.5 G1.
//
// Workspace automation rules: trigger → condition → action. Admin/head
// curate; managers may read for visibility (the spec keeps the read
// open). Modal-based builder, table list with toggle/edit/delete +
// run-history drawer. Send/dispatch is stubbed in v1 (the action
// stages an Activity row instead of actually sending) — see
// `app/automation_builder/services._send_template_action` for the
// rationale.
import { useState } from "react";
import { Loader2, Plus, Workflow } from "lucide-react";

import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  useAutomations,
  useDeleteAutomation,
} from "@/lib/hooks/use-automations";
import { useMe } from "@/lib/hooks/use-me";
import type { AutomationOut } from "@/lib/types";

import { AutomationEditor } from "@/components/automations/AutomationEditor";
import { AutomationsTable } from "@/components/automations/AutomationsTable";
import { DeleteAutomationModal } from "@/components/automations/DeleteAutomationModal";
import { RunsDrawer } from "@/components/automations/RunsDrawer";

export default function AutomationsPage() {
  const me = useMe();
  const listQuery = useAutomations();
  const del = useDeleteAutomation();

  const isAdminOrHead =
    me.data?.role === "admin" || me.data?.role === "head";
  const items = listQuery.data ?? [];

  const [editing, setEditing] = useState<AutomationOut | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [runsFor, setRunsFor] = useState<AutomationOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AutomationOut | null>(null);

  function openCreate() {
    setEditing(null);
    setEditorOpen(true);
  }

  function openEdit(a: AutomationOut) {
    setEditing(a);
    setEditorOpen(true);
  }

  function onDelete(a: AutomationOut) {
    setDeleteTarget(a);
  }

  function confirmDelete() {
    if (!deleteTarget) return;
    del.mutate(deleteTarget.id);
    setDeleteTarget(null);
  }

  return (
    <div className={pageContainerVariants({ surface: "data" })}>
      <PageHeader
        icon={<Workflow size={20} />}
        title="Автоматизации"
        subtitle="Когда происходит событие → проверяем условие → выполняем действие. В v1 отправка email/tg/sms ставится в очередь как Activity — настоящая отправка приедет в 2.6+."
        actions={
          isAdminOrHead && (
            <button
              type="button"
              onClick={openCreate}
              className="inline-flex items-center gap-1.5 bg-brand-accent text-white rounded-full px-3.5 py-1.5 text-xs font-semibold hover:bg-brand-accent/90 active:scale-[0.98] transition duration-300"
            >
              <Plus size={13} />
              Новая автоматизация
            </button>
          )
        }
      />

      {listQuery.isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={20} className="animate-spin text-brand-muted" />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-brand-bg/60 border border-brand-border rounded-card px-6 py-12 text-center">
          <Workflow size={20} className="text-brand-muted mx-auto mb-2" />
          <p className="text-sm text-brand-muted">Автоматизаций пока нет.</p>
          <p className="text-xs text-brand-muted mt-1">
            Например: «когда лид перешёл в Pilot → создать задачу
            ‘связаться с ЛПР’».
          </p>
        </div>
      ) : (
        <AutomationsTable
          items={items}
          isAdminOrHead={isAdminOrHead}
          deletePending={del.isPending}
          onShowRuns={setRunsFor}
          onEdit={openEdit}
          onDelete={onDelete}
        />
      )}

      {editorOpen && (
        <AutomationEditor
          automation={editing}
          onClose={() => setEditorOpen(false)}
        />
      )}

      {runsFor && (
        <RunsDrawer
          automation={runsFor}
          onClose={() => setRunsFor(null)}
        />
      )}

      {deleteTarget && (
        <DeleteAutomationModal
          automation={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  );
}
