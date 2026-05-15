"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ClipboardList,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import { clsx } from "clsx";

import { T } from "@/lib/design-system";
import { useMe } from "@/lib/hooks/use-me";
import {
  useDeleteForm,
  useForms,
  useToggleFormActive,
} from "@/lib/hooks/use-forms";
import { relativeTime } from "@/lib/relative-time";
import { FormEditor } from "@/components/forms/FormEditor";
import type { WebFormOut } from "@/lib/types";


export default function FormsPage() {
  const router = useRouter();
  const { data: me, isLoading: meLoading } = useMe();
  const formsQuery = useForms();
  const toggleActive = useToggleFormActive();
  const deleteForm = useDeleteForm();

  const [editing, setEditing] = useState<WebFormOut | null>(null);
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<WebFormOut | null>(null);

  // Role guard — admin/head only. Wait for `me` to resolve before
  // bouncing so freshly-loaded admins don't get redirected to /today
  // during the first render.
  useEffect(() => {
    if (meLoading) return;
    if (!me) return;
    if (me.role !== "admin" && me.role !== "head") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      router.replace("/today" as any);
    }
  }, [me, meLoading, router]);

  const items = formsQuery.data?.items ?? [];

  function openEditor(form: WebFormOut) {
    setEditing(form);
  }

  function openCreator() {
    setCreating(true);
  }

  function closeEditor() {
    setEditing(null);
    setCreating(false);
  }

  function handleDelete() {
    if (!confirmDelete) return;
    deleteForm.mutate(confirmDelete.id, {
      onSuccess: () => setConfirmDelete(null),
    });
  }

  if (meLoading || (!me && !formsQuery.isError)) {
    return (
      <div className="flex-1 flex items-center justify-center min-h-[60vh]">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }

  if (me && me.role !== "admin" && me.role !== "head") {
    // Already kicking off the redirect via useEffect — render nothing
    // to avoid a flash of forbidden content.
    return null;
  }

  return (
    <>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b border-black/5 px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-baseline gap-2">
            <h1 className="type-card-title">Формы</h1>
            <span className="text-muted-3 text-xs font-mono tabular-nums">
              {items.length}
            </span>
          </div>
          <button
            onClick={openCreator}
            className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-4 py-2 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-ink/90 active:scale-[0.98]"
          >
            <Plus size={15} />
            Новая форма
          </button>
        </div>
      </div>

      <div className="px-6 py-5">
        {formsQuery.isLoading && (
          <div className="flex justify-center py-12">
            <Loader2 size={20} className="animate-spin text-muted-2" />
          </div>
        )}

        {formsQuery.isError && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-rose/10 text-rose text-sm">
            <AlertCircle size={14} />
            Не удалось загрузить формы.
          </div>
        )}

        {!formsQuery.isLoading && !formsQuery.isError && items.length === 0 && (
          <EmptyState onCreate={openCreator} />
        )}

        {items.length > 0 && (
          <div className="rounded-2xl border border-black/5 bg-white overflow-hidden">
            <div className={`grid grid-cols-[1fr_180px_90px_110px_140px_100px] items-center gap-3 px-4 py-2.5 bg-canvas border-b border-black/5 ${T.mono} uppercase text-muted-2`}>
              <span>Название</span>
              <span>Slug</span>
              <span className="text-right">Подач</span>
              <span>Активна</span>
              <span>Создана</span>
              <span />
            </div>
            <div className="divide-y divide-black/5">
              {items.map((form) => (
                <FormRow
                  key={form.id}
                  form={form}
                  onClick={() => openEditor(form)}
                  onToggleActive={(next) =>
                    toggleActive.mutate({
                      id: form.id,
                      is_active: next,
                    })
                  }
                  onDelete={() => setConfirmDelete(form)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <FormEditor
        open={creating || !!editing}
        form={editing ?? undefined}
        onClose={closeEditor}
        onSaved={(saved) => {
          // Editor stays open and switches to edit-mode for the saved
          // record so the manager can immediately copy the embed code.
          setCreating(false);
          setEditing(saved);
        }}
      />

      {confirmDelete && (
        <ConfirmDeleteModal
          form={confirmDelete}
          isPending={deleteForm.isPending}
          onCancel={() => setConfirmDelete(null)}
          onConfirm={handleDelete}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function FormRow({
  form,
  onClick,
  onToggleActive,
  onDelete,
}: {
  form: WebFormOut;
  onClick: () => void;
  onToggleActive: (next: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className="grid grid-cols-[1fr_180px_90px_110px_140px_100px] items-center gap-3 px-4 py-3 cursor-pointer hover:bg-canvas/50 transition-colors"
    >
      <div className="min-w-0">
        <div className="text-sm font-bold text-ink truncate">{form.name}</div>
        {form.redirect_url && (
          <div className={`${T.mono} text-muted-3 truncate`}>
            → {form.redirect_url}
          </div>
        )}
      </div>
      <span className={`${T.mono} text-muted-2 truncate`}>
        /{form.slug}
      </span>
      <span className="text-right text-sm font-mono text-ink tabular-nums">
        {form.submissions_count}
      </span>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onToggleActive(!form.is_active);
        }}
        className={clsx(
          "relative inline-flex w-9 h-5 rounded-pill transition-colors",
          form.is_active ? "bg-brand-accent" : "bg-black/15",
        )}
        aria-pressed={form.is_active}
        aria-label={form.is_active ? "Деактивировать форму" : "Активировать форму"}
      >
        <span
          className={clsx(
            "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform",
            form.is_active && "translate-x-4",
          )}
        />
      </button>
      <span className={`${T.mono} text-muted-3`}>
        {relativeTime(form.created_at)}
      </span>
      <div className="flex items-center justify-end">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="p-1.5 rounded-lg text-muted-3 hover:bg-canvas hover:text-rose-600 transition-colors"
          aria-label="Удалить форму"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-12 h-12 rounded-full bg-canvas flex items-center justify-center mb-3">
        <ClipboardList size={22} className="text-muted-3" />
      </div>
      <div className="text-sm font-bold text-ink">Пока нет ни одной формы</div>
      <p className="text-sm text-muted-2 mt-1 mb-4 max-w-[24rem]">
        Создайте форму, чтобы лиды с лендинга приходили в CRM автоматически —
        без ручного копирования из почты.
      </p>
      <button
        onClick={onCreate}
        className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-4 py-2 text-sm font-semibold hover:bg-ink/90"
      >
        <Plus size={15} />
        Новая форма
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Confirm delete modal
// ---------------------------------------------------------------------------

function ConfirmDeleteModal({
  form,
  isPending,
  onCancel,
  onConfirm,
}: {
  form: WebFormOut;
  isPending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50 backdrop-blur-[2px]"
        onClick={onCancel}
        aria-hidden
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div
          role="dialog"
          aria-modal="true"
          className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-md p-5"
        >
          <h2 className="type-card-title text-ink">
            Удалить форму?
          </h2>
          <p className="text-sm text-muted mt-2">
            Форма «{form.name}» будет деактивирована — embed-код вернёт{" "}
            <span className="font-mono">410 Gone</span>, лиды перестанут
            приходить. История подач (
            <span className="font-mono">{form.submissions_count}</span>)
            сохранится для отчётности.
          </p>
          <div className="mt-5 flex items-center justify-end gap-2">
            <button
              onClick={onCancel}
              disabled={isPending}
              className="text-sm font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
            >
              Отмена
            </button>
            <button
              onClick={onConfirm}
              disabled={isPending}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-pill bg-rose-600 text-white text-sm font-semibold hover:bg-rose-600/90 disabled:opacity-40 transition-all duration-300"
            >
              {isPending && <Loader2 size={13} className="animate-spin" />}
              Деактивировать
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
