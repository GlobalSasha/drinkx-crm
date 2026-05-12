"use client";

import { useState } from "react";
import {
  Mail,
  MessageCircle,
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
  PhoneMissed,
  Play,
  Loader2,
  X,
} from "lucide-react";

import {
  useAssignInboxMessage,
  useInboxUnmatchedMessages,
} from "@/lib/hooks/use-inbox";
import { useLeads } from "@/lib/hooks/use-leads";
import type { InboxMessageOut, LeadOut } from "@/lib/types";

function getMeta(channel: string): {
  icon: typeof Mail;
  label: string;
  badgeClass: string;
} {
  switch (channel) {
    case "telegram":
      return { icon: MessageCircle, label: "Telegram", badgeClass: "bg-sky-100 text-sky-700 border-sky-200" };
    case "max":
      return { icon: MessageCircle, label: "MAX", badgeClass: "bg-violet-100 text-violet-700 border-violet-200" };
    case "phone":
      return { icon: Phone, label: "Телефон", badgeClass: "bg-amber-100 text-amber-700 border-amber-200" };
    default:
      return { icon: Mail, label: channel, badgeClass: "bg-black/5 text-muted-2 border-black/5" };
  }
}

function getCallIcon(msg: InboxMessageOut) {
  if (msg.call_status === "missed") return PhoneMissed;
  return msg.direction === "outbound" ? PhoneOutgoing : PhoneIncoming;
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatCallDuration(seconds: number | null | undefined): string {
  const s = seconds ?? 0;
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function LeadSearchPicker({
  onPick,
  onClose,
}: {
  onPick: (lead: LeadOut) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
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

      <div className="max-h-[260px] overflow-y-auto flex flex-col gap-0.5">
        {items.length === 0 && (
          <div className="text-[11px] text-muted-3 px-2 py-3">Ничего не найдено</div>
        )}
        {items.map((l) => (
          <button
            key={l.id}
            onClick={() => onPick(l)}
            className="text-left px-2 py-1.5 rounded-lg hover:bg-canvas transition-colors"
          >
            <div className="text-sm font-semibold text-ink truncate">{l.company_name}</div>
            <div className="text-[11px] font-mono text-muted-3 truncate">
              {l.city || "—"} · {l.segment || "—"}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function UnmatchedRow({ msg }: { msg: InboxMessageOut }) {
  const assign = useAssignInboxMessage();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [hidden, setHidden] = useState(false);

  if (hidden) return null;

  const { icon: ChannelIcon, label: channelLabel, badgeClass } = getMeta(msg.channel);
  const isPhone = msg.channel === "phone";
  const PhoneStateIcon = isPhone ? getCallIcon(msg) : null;
  const preview = isPhone
    ? msg.summary?.trim() ||
      msg.body ||
      `${msg.direction === "outbound" ? "Исходящий" : "Входящий"} звонок, ${formatCallDuration(msg.call_duration)}`
    : msg.body || "(пустое сообщение)";

  function handlePick(lead: LeadOut) {
    setPickerOpen(false);
    assign.mutate(
      { id: msg.id, lead_id: lead.id },
      {
        onSuccess: () => setHidden(true),
      },
    );
  }

  return (
    <div className="rounded-xl border border-black/5 bg-white p-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold ${badgeClass}`}
          >
            {PhoneStateIcon ? <PhoneStateIcon size={12} /> : <ChannelIcon size={12} />}
            {channelLabel}
          </span>
          <span className="text-[11px] font-mono text-muted-3 truncate">
            от {msg.sender_id || "—"}
          </span>
          <span className="text-[11px] font-mono text-muted-3">·</span>
          <span className="text-[11px] font-mono text-muted-3">
            {formatDateTime(msg.created_at)}
          </span>
        </div>

        <div className="text-sm text-ink whitespace-pre-wrap break-words">{preview}</div>

        {isPhone && msg.media_url && (
          <a
            href={msg.media_url}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-brand-accent hover:underline"
          >
            <Play size={12} />
            Запись
          </a>
        )}
      </div>

      <div className="flex flex-wrap gap-2 md:flex-nowrap shrink-0">
        <div className="relative">
          <button
            onClick={() => setPickerOpen((v) => !v)}
            disabled={assign.isPending}
            className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-black/5 text-ink hover:bg-black/10 disabled:opacity-50"
          >
            {assign.isPending ? (
              <span className="inline-flex items-center gap-1">
                <Loader2 size={12} className="animate-spin" /> Привязка…
              </span>
            ) : (
              "Привязать к лиду"
            )}
          </button>
          {pickerOpen && (
            <LeadSearchPicker onPick={handlePick} onClose={() => setPickerOpen(false)} />
          )}
        </div>
      </div>
    </div>
  );
}

export function UnmatchedMessagesSection() {
  const { data, isLoading, isError } = useInboxUnmatchedMessages(1);
  const items = data?.items ?? [];

  if (isLoading) {
    return (
      <section className="mt-10">
        <header className="mb-3">
          <h2 className="text-base font-bold text-ink">Мессенджеры и звонки</h2>
        </header>
        <div className="text-sm text-muted py-6 text-center">Загрузка…</div>
      </section>
    );
  }

  if (isError) {
    return (
      <section className="mt-10">
        <header className="mb-3">
          <h2 className="text-base font-bold text-ink">Мессенджеры и звонки</h2>
        </header>
        <div className="text-sm text-red-700 py-6 text-center">
          Не удалось загрузить нематченные сообщения.
        </div>
      </section>
    );
  }

  if (items.length === 0) return null;

  return (
    <section className="mt-10">
      <header className="mb-3 flex items-baseline justify-between">
        <h2 className="text-base font-bold text-ink">Мессенджеры и звонки</h2>
        <span className="text-[11px] font-mono text-muted-3">
          {items.length} {items.length === 1 ? "сообщение" : "сообщений"}
        </span>
      </header>
      <div className="flex flex-col gap-2.5">
        {items.map((m) => (
          <UnmatchedRow key={m.id} msg={m} />
        ))}
      </div>
    </section>
  );
}
