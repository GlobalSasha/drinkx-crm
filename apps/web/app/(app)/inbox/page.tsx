"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Inbox as InboxIcon,
  Loader2,
  Mail,
  X,
} from "lucide-react";
import { clsx } from "clsx";

import {
  useConfirmItem,
  useConnectGmail,
  useDismissItem,
  useInboxPending,
} from "@/lib/hooks/use-inbox";
import { useLeads } from "@/lib/hooks/use-leads";
import { relativeTime } from "@/lib/relative-time";
import type { InboxItemOut, LeadOut, SuggestedAction } from "@/lib/types";

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncate(s: string | null | undefined, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function suggestionChipLabel(s: SuggestedAction | null): string | null {
  if (!s || !s.action || s.action === "ignore") return null;
  if (s.action === "create_lead") {
    return s.company_name
      ? `Создать карточку: ${s.company_name}`
      : "Создать карточку";
  }
  if (s.action === "add_contact") {
    return s.company_name
      ? `Добавить контакт в: ${s.company_name}`
      : "Добавить контакт";
  }
  if (s.action === "match_lead") return "Привязать к лиду";
  return null;
}

function suggestionChipTone(s: SuggestedAction | null): string {
  if (!s) return "bg-black/5 text-muted-2";
  if (s.action === "create_lead") return "bg-emerald-500/10 text-emerald-700";
  if (s.action === "add_contact") return "bg-blue-500/10 text-blue-700";
  if (s.action === "match_lead") return "bg-black/5 text-muted-2";
  return "bg-black/5 text-muted-2";
}

// ---------------------------------------------------------------------------
// Lead-search dropdown (used by "Привязать к лиду")
// ---------------------------------------------------------------------------

function LeadSearchDropdown({
  onPick,
  onClose,
}: {
  onPick: (lead: LeadOut, mode: "match_lead" | "add_contact") => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<LeadOut | null>(null);
  const { data } = useLeads({ q: q || undefined, page_size: 12 });
  const items = data?.items ?? [];

  return (
    <div className="absolute right-0 top-full mt-1 w-[320px] bg-white rounded-xl border border-black/10 shadow-lg z-30 p-2">
      <div className="flex items-center justify-between gap-2 mb-2">
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Найти лид по компании…"
          className="flex-1 text-sm px-2 py-1.5 rounded-lg bg-canvas border border-black/5 outline-none focus:border-brand-accent"
        />
        <button
          onClick={onClose}
          className="p-1 rounded-lg text-muted-3 hover:bg-black/5"
          aria-label="Закрыть"
        >
          <X size={14} />
        </button>
      </div>

      {!picked && (
        <div className="max-h-[260px] overflow-y-auto flex flex-col gap-0.5">
          {items.length === 0 && (
            <div className="text-[11px] text-muted-3 px-2 py-3">
              Ничего не найдено
            </div>
          )}
          {items.map((l) => (
            <button
              key={l.id}
              onClick={() => setPicked(l)}
              className="text-left px-2 py-1.5 rounded-lg hover:bg-canvas transition-colors"
            >
              <div className="text-sm font-semibold text-ink truncate">
                {l.company_name}
              </div>
              <div className="text-[11px] font-mono text-muted-3 truncate">
                {l.city || "—"} · {l.segment || "—"}
              </div>
            </button>
          ))}
        </div>
      )}

      {picked && (
        <div className="flex flex-col gap-1.5">
          <div className="text-[11px] font-mono text-muted-3 px-2 pt-1">
            Выбрано: <span className="font-semibold text-ink">{picked.company_name}</span>
          </div>
          <button
            onClick={() => onPick(picked, "match_lead")}
            className="text-left text-sm px-2 py-2 rounded-lg hover:bg-canvas border border-black/5"
          >
            Добавить как письмо
          </button>
          <button
            onClick={() => onPick(picked, "add_contact")}
            className="text-left text-sm px-2 py-2 rounded-lg hover:bg-canvas border border-black/5"
          >
            Добавить как контакт
          </button>
          <button
            onClick={() => setPicked(null)}
            className="text-[11px] text-muted-3 hover:text-ink py-1"
          >
            ← Назад к поиску
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create-lead modal
// ---------------------------------------------------------------------------

function CreateLeadModal({
  open,
  defaultName,
  onClose,
  onConfirm,
}: {
  open: boolean;
  defaultName: string;
  onClose: () => void;
  onConfirm: (companyName: string) => void;
}) {
  const [name, setName] = useState(defaultName);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-[420px] p-5">
        <h2 className="text-base font-bold text-ink mb-1">Создать карточку</h2>
        <p className="text-[12px] text-muted mb-4">
          Лид попадёт в общую базу (assignment_status=pool) с письмом в активности.
        </p>
        <label className="text-[11px] font-mono text-muted-2 block mb-1">
          Название компании
        </label>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full text-sm px-3 py-2 rounded-lg bg-canvas border border-black/5 outline-none focus:border-brand-accent mb-4"
        />
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="text-sm px-3 py-2 rounded-lg text-muted hover:bg-canvas"
          >
            Отмена
          </button>
          <button
            onClick={() => onConfirm(name.trim() || defaultName)}
            className="text-sm font-semibold px-3 py-2 rounded-lg bg-brand-accent text-white hover:opacity-90"
          >
            Создать
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// One InboxItem row
// ---------------------------------------------------------------------------

function InboxRow({ item }: { item: InboxItemOut }) {
  const confirm = useConfirmItem();
  const dismiss = useDismissItem();
  const [searchOpen, setSearchOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  const isInbound = item.direction !== "outbound";
  const chipLabel = suggestionChipLabel(item.suggested_action);
  const chipTone = suggestionChipTone(item.suggested_action);
  const suggestion = item.suggested_action;
  const showCreateButton =
    !suggestion ||
    suggestion.action === "create_lead" ||
    suggestion.action === "ignore";

  function onCreateLead(companyName: string) {
    setCreateOpen(false);
    confirm.mutate({
      id: item.id,
      body: { action: "create_lead", company_name: companyName },
    });
  }

  function onPickLead(lead: LeadOut, mode: "match_lead" | "add_contact") {
    setSearchOpen(false);
    confirm.mutate({
      id: item.id,
      body: {
        action: mode,
        lead_id: lead.id,
      },
    });
  }

  function onDismiss() {
    // Optimistic UI: hide the row immediately; mutation invalidates the
    // query on settle and the row stays gone.
    setDismissed(true);
    dismiss.mutate(item.id);
  }

  return (
    <div className="rounded-xl border border-black/5 bg-white p-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      {/* Left: meta + body */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1">
          {isInbound ? (
            <span title="Входящее">
              <ArrowLeft size={14} className="text-blue-600" />
            </span>
          ) : (
            <span title="Исходящее">
              <ArrowRight size={14} className="text-emerald-600" />
            </span>
          )}
          <span className="text-[11px] font-mono text-muted-3 truncate">
            {item.from_email}
          </span>
          <span className="text-[11px] font-mono text-muted-3">·</span>
          <span className="text-[11px] font-mono text-muted-3">
            {relativeTime(item.received_at)}
          </span>
        </div>
        <div className="text-sm font-bold text-ink truncate">
          {truncate(item.subject, 80) || "(без темы)"}
        </div>
        <div className="text-[12px] text-muted truncate mt-0.5">
          {truncate(item.body_preview, 140)}
        </div>

        {/* Suggestion row */}
        <div className="mt-2 min-h-[20px]">
          {chipLabel && (
            <span
              className={clsx(
                "inline-flex items-center gap-1 px-2 py-0.5 rounded-pill text-[11px] font-semibold",
                chipTone,
              )}
            >
              {chipLabel}
              {suggestion && typeof suggestion.confidence === "number" && (
                <span className="font-mono text-[10px] opacity-70 ml-0.5">
                  · {Math.round(suggestion.confidence * 100)}%
                </span>
              )}
            </span>
          )}
          {!chipLabel && (
            <span className="inline-flex items-center gap-1 text-[11px] text-muted-3 font-mono">
              <Loader2 size={12} className="animate-spin" />
              AI анализирует…
            </span>
          )}
        </div>
      </div>

      {/* Right: action buttons */}
      <div className="flex flex-wrap gap-2 md:flex-nowrap shrink-0">
        {showCreateButton && (
          <button
            onClick={() => setCreateOpen(true)}
            className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:opacity-90 disabled:opacity-50"
            disabled={confirm.isPending}
          >
            Создать карточку
          </button>
        )}

        <div className="relative">
          <button
            onClick={() => setSearchOpen((v) => !v)}
            className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-black/5 text-ink hover:bg-black/10 disabled:opacity-50"
            disabled={confirm.isPending}
          >
            Привязать к лиду
          </button>
          {searchOpen && (
            <LeadSearchDropdown
              onPick={onPickLead}
              onClose={() => setSearchOpen(false)}
            />
          )}
        </div>

        <button
          onClick={onDismiss}
          className="text-[12px] font-semibold px-3 py-1.5 rounded-lg text-muted-2 hover:bg-black/5 disabled:opacity-50"
          disabled={dismiss.isPending}
        >
          Игнор
        </button>
      </div>

      <CreateLeadModal
        open={createOpen}
        defaultName={
          (suggestion?.company_name as string) ||
          item.from_email.split("@")[1] ||
          ""
        }
        onClose={() => setCreateOpen(false)}
        onConfirm={onCreateLead}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function CallbackBanner() {
  const searchParams = useSearchParams();
  const status = searchParams?.get("status");
  const error = searchParams?.get("error");
  if (status === "ok") {
    return (
      <div className="mb-4 px-4 py-3 rounded-xl bg-emerald-50 text-emerald-800 text-sm">
        Gmail подключён. Мы загрузим письма за последние месяцы — это займёт
        несколько минут.
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="mb-4 px-4 py-3 rounded-xl bg-red-50 text-red-800 text-sm">
        Не удалось подключить Gmail{error ? `: ${error}` : ""}.
      </div>
    );
  }
  return null;
}

export default function InboxPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useInboxPending(page);
  const connect = useConnectGmail();

  const totalPages = useMemo(() => {
    const total = data?.total ?? 0;
    return Math.max(1, Math.ceil(total / PAGE_SIZE));
  }, [data?.total]);

  function handleConnect() {
    connect.mutate(undefined, {
      onSuccess: ({ redirect_url }) => {
        if (redirect_url) window.location.href = redirect_url;
      },
    });
  }

  return (
    <div className="px-6 py-6 md:px-10 md:py-8 max-w-[920px] mx-auto">
      <header className="mb-6">
        <h1 className="text-xl font-extrabold tracking-tight text-ink">
          Входящие
        </h1>
        <p className="text-sm text-muted mt-1">Неразобранные письма</p>
      </header>

      <Suspense fallback={null}>
        <CallbackBanner />
      </Suspense>

      {isLoading && (
        <div className="text-sm text-muted py-12 text-center">Загрузка…</div>
      )}

      {isError && (
        <div className="text-sm text-red-700 py-12 text-center">
          Не удалось загрузить входящие.
        </div>
      )}

      {!isLoading && !isError && (data?.items.length ?? 0) === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-12 h-12 rounded-full bg-canvas flex items-center justify-center mb-3">
            <InboxIcon size={22} className="text-muted-3" />
          </div>
          <div className="text-sm font-bold text-ink">Все письма разобраны</div>
          <p className="text-[12px] text-muted-2 mt-1 mb-4">
            Подключите Gmail, чтобы письма появлялись здесь автоматически.
          </p>
          <button
            onClick={handleConnect}
            disabled={connect.isPending}
            className="inline-flex items-center gap-2 text-sm font-semibold px-4 py-2 rounded-xl bg-brand-accent text-white hover:opacity-90 disabled:opacity-50"
          >
            <Mail size={14} />
            {connect.isPending ? "Подключаем…" : "Подключить Gmail"}
          </button>
        </div>
      )}

      {!isLoading && !isError && (data?.items.length ?? 0) > 0 && (
        <>
          <div className="flex flex-col gap-2.5">
            {data!.items.map((item) => (
              <InboxRow key={item.id} item={item} />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-3 text-[12px] font-mono text-muted-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded-lg hover:bg-black/5 disabled:opacity-40"
                aria-label="Предыдущая"
              >
                <ChevronLeft size={14} />
              </button>
              <span>
                Страница {page} из {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1.5 rounded-lg hover:bg-black/5 disabled:opacity-40"
                aria-label="Следующая"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
