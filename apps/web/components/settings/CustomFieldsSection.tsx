"use client";
// CustomFieldsSection — Sprint 2.4 G3.
//
// Workspace-defined extra fields on Lead. Admin/head-only writes;
// managers can read the list but action buttons hide.
//
// v1 ships definition CRUD only — rendering values on the LeadCard /
// pipeline filters / segments is a 2.4+ polish carryover. The section
// surfaces this so admins don't expect the new field to show up on
// /pipeline immediately.
import { useState } from "react";
import {
  Loader2,
  Pencil,
  Plus,
  Sparkles,
  Tag,
  Trash2,
  X,
} from "lucide-react";

import { ApiError } from "@/lib/api-client";
import {
  useCreateCustomAttribute,
  useCustomAttributes,
  useDeleteCustomAttribute,
  useUpdateCustomAttribute,
} from "@/lib/hooks/use-custom-attributes";
import { useMe } from "@/lib/hooks/use-me";
import type {
  AttributeKind,
  AttributeOption,
  CustomAttributeDefinitionOut,
} from "@/lib/types";

const KIND_LABELS: Record<AttributeKind, string> = {
  text: "Текст",
  number: "Число",
  date: "Дата",
  select: "Список",
};


export function CustomFieldsSection() {
  const me = useMe();
  const listQuery = useCustomAttributes();
  const del = useDeleteCustomAttribute();

  const isAdminOrHead =
    me.data?.role === "admin" || me.data?.role === "head";
  const items = listQuery.data ?? [];

  const [editing, setEditing] = useState<
    CustomAttributeDefinitionOut | null
  >(null);
  const [editorOpen, setEditorOpen] = useState(false);

  function openCreate() {
    setEditing(null);
    setEditorOpen(true);
  }

  function openEdit(def: CustomAttributeDefinitionOut) {
    setEditing(def);
    setEditorOpen(true);
  }

  function onDelete(def: CustomAttributeDefinitionOut) {
    if (
      !window.confirm(
        `Удалить поле «${def.label}»? Все сохранённые значения тоже пропадут.`,
      )
    ) {
      return;
    }
    del.mutate(def.id);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-extrabold tracking-tight">
            Кастомные поля
          </h2>
          <p className="text-xs text-muted-2 mt-0.5">
            Дополнительные атрибуты лида под нужды воронки. v1 — только
            настройка; отображение на карточке лида приедет позже.
          </p>
        </div>
        {isAdminOrHead && (
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-3.5 py-1.5 text-xs font-semibold hover:bg-ink/90 active:scale-[0.98] transition-all duration-300"
          >
            <Plus size={13} />
            Новое поле
          </button>
        )}
      </div>

      {listQuery.isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={20} className="animate-spin text-muted-2" />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-canvas/60 border border-black/5 rounded-2xl px-6 py-12 text-center">
          <Sparkles size={20} className="text-muted-2 mx-auto mb-2" />
          <p className="text-sm text-muted">Пока нет кастомных полей.</p>
          <p className="text-[11px] text-muted-3 mt-1">
            Например: «Регион», «Тип заведения», «Источник лида».
          </p>
        </div>
      ) : (
        <div className="bg-white border border-black/5 rounded-2xl shadow-soft overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-canvas">
              <tr className="text-left text-[10px] font-mono uppercase tracking-wide text-muted-3">
                <th className="px-4 py-2 font-semibold">Метка</th>
                <th className="px-4 py-2 font-semibold">Ключ</th>
                <th className="px-4 py-2 font-semibold">Тип</th>
                <th className="px-4 py-2 font-semibold">Обязательно</th>
                {isAdminOrHead && (
                  <th className="px-4 py-2 font-semibold text-right">
                    Действия
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((def) => (
                <tr
                  key={def.id}
                  className="border-t border-black/5 hover:bg-canvas/40 transition-colors"
                >
                  <td className="px-4 py-3 font-semibold text-ink">
                    <span className="inline-flex items-center gap-1.5">
                      <Tag size={11} className="text-muted-3" />
                      {def.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs font-mono text-muted">
                    {def.key}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {KIND_LABELS[def.kind]}
                    {def.kind === "select" && def.options_json && (
                      <span className="text-muted-3 ml-1">
                        · {def.options_json.length} опций
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {def.is_required ? (
                      <span className="text-warning font-semibold">Да</span>
                    ) : (
                      <span className="text-muted-3">—</span>
                    )}
                  </td>
                  {isAdminOrHead && (
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => openEdit(def)}
                          className="text-muted hover:text-ink p-1.5 rounded-md hover:bg-black/5 transition-colors"
                          title="Редактировать"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={() => onDelete(def)}
                          disabled={del.isPending}
                          className="text-muted hover:text-rose p-1.5 rounded-md hover:bg-rose/5 transition-colors disabled:opacity-40"
                          title="Удалить"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editorOpen && (
        <CustomFieldEditor
          definition={editing}
          onClose={() => setEditorOpen(false)}
        />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Editor modal — create OR edit
// ---------------------------------------------------------------------------

function CustomFieldEditor({
  definition,
  onClose,
}: {
  definition: CustomAttributeDefinitionOut | null;
  onClose: () => void;
}) {
  const isEdit = definition !== null;
  const create = useCreateCustomAttribute();
  const update = useUpdateCustomAttribute(definition?.id ?? "");

  const [key, setKey] = useState(definition?.key ?? "");
  const [label, setLabel] = useState(definition?.label ?? "");
  const [kind, setKind] = useState<AttributeKind>(
    definition?.kind ?? "text",
  );
  const [isRequired, setIsRequired] = useState(
    definition?.is_required ?? false,
  );
  const [options, setOptions] = useState<AttributeOption[]>(
    definition?.options_json ?? [],
  );
  const [error, setError] = useState<string | null>(null);

  const pending = create.isPending || update.isPending;

  function addOption() {
    setOptions([...options, { value: "", label: "" }]);
  }
  function removeOption(idx: number) {
    setOptions(options.filter((_, i) => i !== idx));
  }
  function updateOption(idx: number, patch: Partial<AttributeOption>) {
    setOptions(
      options.map((o, i) => (i === idx ? { ...o, ...patch } : o)),
    );
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!label.trim()) {
      setError("Метка обязательна.");
      return;
    }

    const optionsPayload =
      kind === "select"
        ? options
            .map((o) => ({ value: o.value.trim(), label: o.label.trim() }))
            .filter((o) => o.value && o.label)
        : null;
    if (kind === "select" && (!optionsPayload || optionsPayload.length === 0)) {
      setError("Для типа «Список» нужен хотя бы один вариант.");
      return;
    }

    const onErr = (err: ApiError) => {
      const detail =
        err.body && typeof err.body === "object"
          ? (err.body as { detail?: unknown }).detail
          : null;
      if (detail && typeof detail === "object" && "message" in detail) {
        setError(String((detail as { message: unknown }).message));
      } else {
        setError("Не удалось сохранить.");
      }
    };

    if (isEdit) {
      update.mutate(
        {
          label: label.trim(),
          options_json: optionsPayload,
          is_required: isRequired,
        },
        { onSuccess: onClose, onError: onErr },
      );
    } else {
      if (!key.trim()) {
        setError("Ключ обязателен.");
        return;
      }
      create.mutate(
        {
          key: key.trim(),
          label: label.trim(),
          kind,
          options_json: optionsPayload,
          is_required: isRequired,
        },
        { onSuccess: onClose, onError: onErr },
      );
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-black/5">
          <h3 className="text-base font-extrabold">
            {isEdit ? "Редактировать поле" : "Новое поле"}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-muted hover:text-ink p-1"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={onSubmit} className="px-5 py-4 space-y-3">
          <div>
            <label className="text-[11px] font-mono uppercase tracking-wide text-muted-3">
              Метка
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Регион"
              className="mt-1 w-full bg-canvas border border-black/10 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-accent"
            />
          </div>

          <div>
            <label className="text-[11px] font-mono uppercase tracking-wide text-muted-3">
              Ключ {isEdit && <span className="text-muted-3">(нельзя менять)</span>}
            </label>
            <input
              type="text"
              value={key}
              onChange={(e) =>
                setKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))
              }
              disabled={isEdit}
              placeholder="region"
              className="mt-1 w-full bg-canvas border border-black/10 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:border-accent disabled:opacity-60"
            />
            <p className="text-[10px] text-muted-3 mt-1">
              Латиница, цифры, подчёркивания.
            </p>
          </div>

          <div>
            <label className="text-[11px] font-mono uppercase tracking-wide text-muted-3">
              Тип {isEdit && <span className="text-muted-3">(нельзя менять)</span>}
            </label>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as AttributeKind)}
              disabled={isEdit}
              className="mt-1 w-full bg-canvas border border-black/10 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-accent disabled:opacity-60"
            >
              {(Object.keys(KIND_LABELS) as AttributeKind[]).map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </div>

          {kind === "select" && (
            <div>
              <div className="flex items-center justify-between">
                <label className="text-[11px] font-mono uppercase tracking-wide text-muted-3">
                  Варианты
                </label>
                <button
                  type="button"
                  onClick={addOption}
                  className="text-[11px] text-accent font-semibold hover:underline"
                >
                  + добавить
                </button>
              </div>
              <div className="space-y-1 mt-1">
                {options.map((opt, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <input
                      type="text"
                      value={opt.value}
                      onChange={(e) =>
                        updateOption(i, { value: e.target.value })
                      }
                      placeholder="value"
                      className="flex-1 bg-canvas border border-black/10 rounded-lg px-2 py-1 text-xs font-mono focus:outline-none focus:border-accent"
                    />
                    <input
                      type="text"
                      value={opt.label}
                      onChange={(e) =>
                        updateOption(i, { label: e.target.value })
                      }
                      placeholder="Метка"
                      className="flex-1 bg-canvas border border-black/10 rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-accent"
                    />
                    <button
                      type="button"
                      onClick={() => removeOption(i)}
                      className="text-muted-2 hover:text-rose p-1"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
                {options.length === 0 && (
                  <p className="text-[10px] text-muted-3">
                    Нужен хотя бы один вариант.
                  </p>
                )}
              </div>
            </div>
          )}

          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={isRequired}
              onChange={(e) => setIsRequired(e.target.checked)}
              className="rounded"
            />
            <span>Обязательное поле</span>
          </label>

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="submit"
              disabled={pending}
              className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-4 py-2 text-sm font-semibold hover:bg-ink/90 disabled:opacity-40 transition-all duration-300"
            >
              {pending && <Loader2 size={13} className="animate-spin" />}
              {isEdit ? "Сохранить" : "Создать"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="text-sm text-muted hover:text-ink"
            >
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
