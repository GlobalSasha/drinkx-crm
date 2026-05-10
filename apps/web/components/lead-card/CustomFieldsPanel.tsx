"use client";
// CustomFieldsPanel — Sprint 2.6 G4.
//
// Renders the workspace's custom-attribute definitions as inline-edit
// rows on the LeadCard. Click a value → it becomes an input;
// Enter / blur saves; Escape cancels. No edit-mode toggle; no save
// button. Empty values render as «не заполнено» in italic muted text.
//
// `useUpsertLeadAttribute` echoes the updated row from the backend,
// so the displayed value always reflects what's persisted (no
// optimistic-then-revert risk).
import { useEffect, useRef, useState } from "react";
import { Loader2, Pencil } from "lucide-react";

import { ApiError } from "@/lib/api-client";
import {
  useLeadAttributes,
  useUpsertLeadAttribute,
} from "@/lib/hooks/use-lead-attributes";
import type { LeadAttributeOut } from "@/lib/types";

interface Props {
  leadId: string;
}

const _DATE_FMT = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

function formatDisplay(attr: LeadAttributeOut): string {
  if (attr.value === null || attr.value === undefined || attr.value === "") {
    return "";
  }
  if (attr.kind === "number") {
    const n = Number(attr.value);
    if (Number.isFinite(n)) {
      return n.toLocaleString("ru-RU");
    }
    return String(attr.value);
  }
  if (attr.kind === "date") {
    // Backend returns ISO date string for date-kind values.
    const d = new Date(String(attr.value));
    if (Number.isNaN(d.getTime())) return String(attr.value);
    return _DATE_FMT.format(d);
  }
  if (attr.kind === "select" && attr.options_json) {
    const match = attr.options_json.find(
      (o) => o.value === String(attr.value),
    );
    if (match) return match.label;
  }
  return String(attr.value);
}


export function CustomFieldsPanel({ leadId }: Props) {
  const listQuery = useLeadAttributes(leadId);
  const items = listQuery.data ?? [];

  if (listQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-3">
        <Loader2 size={12} className="animate-spin" />
        Загрузка кастомных полей…
      </div>
    );
  }

  if (items.length === 0) {
    // No definitions in this workspace — render nothing rather than
    // an empty section. Admin can add fields in /settings → Кастомные.
    return null;
  }

  return (
    <section className="bg-white border border-black/5 rounded-2xl shadow-soft p-4">
      <h3 className="text-xs font-mono uppercase tracking-[0.18em] text-muted-3 mb-3">
        Кастомные поля
      </h3>
      <div className="divide-y divide-black/5">
        {items.map((attr) => (
          <CustomFieldRow key={attr.definition_id} leadId={leadId} attr={attr} />
        ))}
      </div>
    </section>
  );
}


function CustomFieldRow({
  leadId,
  attr,
}: {
  leadId: string;
  attr: LeadAttributeOut;
}) {
  const upsert = useUpsertLeadAttribute(leadId);

  // Editing state — `null` when read-only, otherwise the current
  // input draft. Initialised from the persisted value when entering
  // edit mode.
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | HTMLSelectElement | null>(null);

  // Auto-focus when entering edit mode.
  useEffect(() => {
    if (draft !== null && inputRef.current) {
      inputRef.current.focus();
      // Cursor at end for text inputs — avoids selecting all on click
      if (inputRef.current instanceof HTMLInputElement) {
        const v = inputRef.current.value;
        inputRef.current.setSelectionRange(v.length, v.length);
      }
    }
  }, [draft]);

  function startEdit() {
    // Pre-fill the input with the existing value as a string. For
    // date kind, value comes from backend as ISO yyyy-mm-dd which
    // <input type="date"> accepts directly.
    if (attr.value === null || attr.value === undefined) {
      setDraft("");
    } else {
      setDraft(String(attr.value));
    }
    setError(null);
  }

  function cancel() {
    setDraft(null);
    setError(null);
  }

  function save(nextValue: string | null) {
    setError(null);
    upsert.mutate(
      { definition_id: attr.definition_id, value: nextValue },
      {
        onSuccess: () => setDraft(null),
        onError: (err: ApiError) => {
          const detail =
            err.body && typeof err.body === "object"
              ? (err.body as { detail?: unknown }).detail
              : null;
          if (detail && typeof detail === "object" && "message" in detail) {
            setError(String((detail as { message: unknown }).message));
          } else {
            setError("Не удалось сохранить.");
          }
        },
      },
    );
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      save(draft ?? "");
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  }

  const display = formatDisplay(attr);

  return (
    <div className="flex items-start gap-3 py-2.5">
      <div className="text-xs text-muted-2 w-[130px] shrink-0 pt-1">
        {attr.label}
        {attr.is_required && (
          <span className="text-warning ml-1" title="Обязательное">
            *
          </span>
        )}
      </div>

      <div className="flex-1 min-w-0">
        {draft === null ? (
          <button
            type="button"
            onClick={startEdit}
            className="group flex items-center gap-2 text-left w-full hover:bg-canvas/60 rounded-lg px-1.5 py-1 transition-colors min-h-[28px]"
          >
            {display ? (
              <span className="text-sm text-ink truncate">{display}</span>
            ) : (
              <span className="text-xs text-muted-3 italic">
                не заполнено
              </span>
            )}
            <Pencil
              size={11}
              className="text-muted-3 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
            />
          </button>
        ) : (
          <CustomFieldEditor
            attr={attr}
            draft={draft}
            setDraft={setDraft}
            inputRef={inputRef}
            onCommit={(v) => save(v)}
            onCancel={cancel}
            onKey={handleKey}
            pending={upsert.isPending}
          />
        )}
        {error && (
          <p className="text-[11px] text-rose mt-0.5 px-1.5">{error}</p>
        )}
      </div>
    </div>
  );
}


function CustomFieldEditor({
  attr,
  draft,
  setDraft,
  inputRef,
  onCommit,
  onCancel,
  onKey,
  pending,
}: {
  attr: LeadAttributeOut;
  draft: string;
  setDraft: (v: string) => void;
  inputRef: React.MutableRefObject<HTMLInputElement | HTMLSelectElement | null>;
  onCommit: (v: string) => void;
  onCancel: () => void;
  onKey: (e: React.KeyboardEvent) => void;
  pending: boolean;
}) {
  // Select kind — saves immediately on change (matches the spec's
  // «selection saves immediately» semantics).
  if (attr.kind === "select") {
    const options = attr.options_json ?? [];
    return (
      <div className="flex items-center gap-2">
        <select
          ref={(el) => {
            inputRef.current = el;
          }}
          value={draft}
          onChange={(e) => onCommit(e.target.value)}
          onBlur={onCancel}
          onKeyDown={onKey}
          disabled={pending}
          className="bg-canvas border border-brand-accent/30 rounded-lg px-2 py-1 text-sm focus:outline-none focus:border-brand-accent w-full max-w-[280px] disabled:opacity-50"
        >
          <option value="">— очистить —</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {pending && <Loader2 size={12} className="animate-spin text-muted-2" />}
      </div>
    );
  }

  const inputType =
    attr.kind === "number"
      ? "number"
      : attr.kind === "date"
        ? "date"
        : "text";

  return (
    <div className="flex items-center gap-2">
      <input
        ref={(el) => {
          inputRef.current = el;
        }}
        type={inputType}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => onCommit(draft)}
        onKeyDown={onKey}
        disabled={pending}
        step={attr.kind === "number" ? "any" : undefined}
        className="bg-canvas border border-brand-accent/30 rounded-lg px-2 py-1 text-sm focus:outline-none focus:border-brand-accent w-full max-w-[280px] disabled:opacity-50"
      />
      {pending && <Loader2 size={12} className="animate-spin text-muted-2" />}
    </div>
  );
}
