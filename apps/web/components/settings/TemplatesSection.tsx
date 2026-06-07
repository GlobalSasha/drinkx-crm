"use client";
// TemplatesSection — Sprint 2.4 G4.
//
// Admin curates reusable message bodies for the upcoming Automation
// Builder (Sprint 2.5). v1 — definition CRUD only; rendering /
// dispatch lives in 2.5. Read-open to every role; create/edit/delete
// hidden for non-admins.
import { useState } from "react";
import { InlineConfirm } from "@/components/ui/InlineConfirm";
import {
  Loader2,
  Mail,
  MessageCircle,
  MessageSquare,
  Pencil,
  Plus,
  ScrollText,
  Trash2,
  X,
} from "lucide-react";

import { T } from "@/lib/design-system";
import { ApiError } from "@/lib/api-client";
import { useMe } from "@/lib/hooks/use-me";
import {
  useCreateTemplate,
  useDeleteTemplate,
  useTemplates,
  useUpdateTemplate,
} from "@/lib/hooks/use-templates";
import type {
  MessageTemplateOut,
  TemplateChannel,
} from "@/lib/types";


const CHANNEL_LABELS: Record<TemplateChannel, string> = {
  email: "Почта",
  tg: "Telegram",
  sms: "SMS",
};

function ChannelIcon({ channel }: { channel: TemplateChannel }) {
  const cls = "text-brand-muted shrink-0";
  if (channel === "email") return <Mail size={12} className={cls} />;
  if (channel === "tg") return <MessageCircle size={12} className={cls} />;
  return <MessageSquare size={12} className={cls} />;
}

function previewText(text: string, max = 60): string {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
}


export function TemplatesSection() {
  const me = useMe();
  const listQuery = useTemplates();
  const del = useDeleteTemplate();

  const isAdmin = me.data?.role === "admin";
  const items = listQuery.data ?? [];

  const [editing, setEditing] = useState<MessageTemplateOut | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);

  function openCreate() {
    setEditing(null);
    setEditorOpen(true);
  }

  function openEdit(t: MessageTemplateOut) {
    setEditing(t);
    setEditorOpen(true);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="type-card-title">Шаблоны</h2>
          <p className="text-xs text-brand-muted mt-0.5">
            Готовые тексты сообщений для email / Telegram / SMS.
            Их будут использовать автоматизации Sprint 2.5 — в v1 это
            только настройка.
          </p>
        </div>
        {isAdmin && (
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-1.5 bg-brand-accent text-white rounded-full px-3.5 py-1.5 text-xs font-semibold hover:bg-brand-accent/90 active:scale-[0.98] transition-all duration-300"
          >
            <Plus size={13} />
            Новый шаблон
          </button>
        )}
      </div>

      {listQuery.isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={20} className="animate-spin text-brand-muted" />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-brand-bg/60 border border-brand-border rounded-card px-6 py-12 text-center">
          <ScrollText size={20} className="text-brand-muted mx-auto mb-2" />
          <p className="text-sm text-brand-muted">Шаблонов пока нет.</p>
          <p className="text-xs text-brand-muted mt-1">
            Например: «Первое касание», «Напоминание о встрече».
          </p>
        </div>
      ) : (
        <div className="bg-white border border-brand-border rounded-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-brand-bg">
              <tr className={`text-left ${T.mono} uppercase text-brand-muted`}>
                <th className="px-4 py-2 font-semibold">Название</th>
                <th className="px-4 py-2 font-semibold">Канал</th>
                <th className="px-4 py-2 font-semibold">Категория</th>
                <th className="px-4 py-2 font-semibold">Текст</th>
                {isAdmin && (
                  <th className="px-4 py-2 font-semibold text-right">
                    Действия
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr
                  key={t.id}
                  className="border-t border-brand-border hover:bg-brand-bg/40 transition-colors"
                >
                  <td className="px-4 py-3 font-semibold text-brand-primary truncate max-w-[200px]">
                    {t.name}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <span className="inline-flex items-center gap-1.5">
                      <ChannelIcon channel={t.channel} />
                      {CHANNEL_LABELS[t.channel]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-brand-muted">
                    {t.category ?? <span className="text-brand-muted">—</span>}
                  </td>
                  <td className="px-4 py-3 text-xs text-brand-muted max-w-[280px] truncate">
                    {previewText(t.text)}
                  </td>
                  {isAdmin && (
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => openEdit(t)}
                          className="text-brand-muted hover:text-brand-primary p-1.5 rounded-md hover:bg-black/5 transition-colors"
                          title="Редактировать"
                        >
                          <Pencil size={13} />
                        </button>
                        <InlineConfirm
                          destructive
                          prompt={`Удалить «${t.name}»?`}
                          confirmLabel="Удалить"
                          busy={del.isPending}
                          onConfirm={() => del.mutate(t.id)}
                        >
                          {(openConfirm) => (
                            <button
                              type="button"
                              onClick={openConfirm}
                              disabled={del.isPending}
                              className="text-brand-muted hover:text-rose p-1.5 rounded-md hover:bg-rose/5 transition-colors disabled:opacity-40"
                              title="Удалить"
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </InlineConfirm>
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
        <TemplateEditor
          template={editing}
          onClose={() => setEditorOpen(false)}
        />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Editor modal — create OR edit
// ---------------------------------------------------------------------------

function TemplateEditor({
  template,
  onClose,
}: {
  template: MessageTemplateOut | null;
  onClose: () => void;
}) {
  const isEdit = template !== null;
  const create = useCreateTemplate();
  const update = useUpdateTemplate(template?.id ?? "");

  const [name, setName] = useState(template?.name ?? "");
  const [channel, setChannel] = useState<TemplateChannel>(
    template?.channel ?? "email",
  );
  const [category, setCategory] = useState(template?.category ?? "");
  const [text, setText] = useState(template?.text ?? "");
  const [error, setError] = useState<string | null>(null);

  const pending = create.isPending || update.isPending;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Название обязательно.");
      return;
    }
    if (!text.trim()) {
      setError("Текст шаблона обязателен.");
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

    const trimmedCategory = category.trim() || null;

    if (isEdit) {
      update.mutate(
        {
          name: name.trim(),
          channel,
          category: trimmedCategory,
          text,
        },
        { onSuccess: onClose, onError: onErr },
      );
    } else {
      create.mutate(
        {
          name: name.trim(),
          channel,
          category: trimmedCategory,
          text,
        },
        { onSuccess: onClose, onError: onErr },
      );
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div className="bg-white rounded-card shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <h3 className="type-card-title">
            {isEdit ? "Редактировать шаблон" : "Новый шаблон"}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-brand-muted hover:text-brand-primary p-1"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={onSubmit} className="px-5 py-4 space-y-3">
          <label className="block">
            <span className={`${T.mono} uppercase text-brand-muted`}>
              Название
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Первое касание"
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            />
          </label>

          <label className="block">
            <span className={`${T.mono} uppercase text-brand-muted`}>
              Канал
            </span>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value as TemplateChannel)}
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            >
              {(Object.keys(CHANNEL_LABELS) as TemplateChannel[]).map((c) => (
                <option key={c} value={c}>
                  {CHANNEL_LABELS[c]}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className={`${T.mono} uppercase text-brand-muted`}>
              Категория <span className="text-brand-muted">(необязательно)</span>
            </span>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="Онбординг"
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
            />
          </label>

          <label className="block">
            <span className={`${T.mono} uppercase text-brand-muted`}>
              Текст
            </span>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              placeholder="Здравствуйте, {{lead.contact_name}}…"
              className="mt-1 w-full bg-brand-bg border border-brand-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 font-mono"
            />
            <p className="text-xs text-brand-muted mt-1">
              Подстановки появятся в Sprint 2.5 — пока обычный текст.
            </p>
          </label>

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="submit"
              disabled={pending}
              className="inline-flex items-center gap-1.5 bg-brand-accent text-white rounded-full px-4 py-2 text-sm font-semibold hover:bg-brand-accent/90 disabled:opacity-40 transition-all duration-300"
            >
              {pending && <Loader2 size={13} className="animate-spin" />}
              {isEdit ? "Сохранить" : "Создать"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="text-sm text-brand-muted hover:text-brand-primary"
            >
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
