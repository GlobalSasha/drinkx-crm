"use client";
import { useMemo, useState } from "react";
import {
  Mail,
  MessageCircle,
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
  PhoneMissed,
  Send,
  Loader2,
  Play,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { ApiError } from "@/lib/api-client";
import { useLeadInbox, useLeadInboxSend, useLeadInboxCall } from "@/lib/hooks/use-lead-inbox";
import type {
  InboxFeedEntry,
  InboxFeedOut,
  LeadOut,
} from "@/lib/types";
import { C } from "@/lib/design-system";

interface Props {
  lead: LeadOut;
}

type FilterKey = "all" | "email" | "telegram" | "phone";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "email", label: "Gmail" },
  { key: "telegram", label: "Telegram" },
  { key: "phone", label: "Телефон" },
];

// Channels the composer can target. MAX is wired on the backend but
// stays out of the composer until G3 / per-manager bot work lands.
type ComposerChannel = "telegram";

const EXTENSION_STORAGE_KEY = "drinkx_manager_extension";

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("ru-RU", {
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

function getChannelMeta(channel: string): {
  icon: typeof Mail;
  label: string;
  badgeClass: string;
} {
  switch (channel) {
    case "email":
      return { icon: Mail, label: "Email", badgeClass: "bg-brand-accent/10 text-brand-accent-text border-brand-accent/20" };
    case "telegram":
      return { icon: MessageCircle, label: "Telegram", badgeClass: "bg-sky-100 text-sky-700 border-sky-200" };
    case "max":
      return { icon: MessageCircle, label: "MAX", badgeClass: "bg-violet-100 text-violet-700 border-violet-200" };
    case "phone":
      return { icon: Phone, label: "Телефон", badgeClass: "bg-amber-100 text-amber-700 border-amber-200" };
    default:
      return { icon: Mail, label: channel, badgeClass: "bg-brand-panel text-brand-muted border-brand-border" };
  }
}

function getCallIcon(entry: InboxFeedEntry) {
  if (entry.call_status === "missed") return PhoneMissed;
  return entry.direction === "outbound" ? PhoneOutgoing : PhoneIncoming;
}

function MessageItem({ entry }: { entry: InboxFeedEntry }) {
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const { icon: ChannelIcon, label: channelLabel, badgeClass } = getChannelMeta(entry.channel);
  const inbound = entry.direction === "inbound";
  const isPhone = entry.channel === "phone";
  const directionLabel = isPhone
    ? entry.call_status === "missed"
      ? "ПРОПУЩЕННЫЙ"
      : inbound
        ? "ВХОДЯЩИЙ"
        : "ИСХОДЯЩИЙ"
    : inbound
      ? "ВХОДЯЩЕЕ"
      : "ОТПРАВЛЕНО";
  const PhoneStateIcon = isPhone ? getCallIcon(entry) : null;
  const summaryText = entry.summary?.trim() ?? null;
  const fallbackBody = isPhone
    ? entry.body ?? (entry.call_duration ? `${inbound ? "Входящий" : "Исходящий"} звонок, ${formatCallDuration(entry.call_duration)}` : "Звонок")
    : entry.body ?? "";

  return (
    <li
      className={`flex flex-col gap-2 px-4 py-3 rounded-2xl border ${
        inbound ? "bg-white border-brand-border" : "bg-brand-soft/60 border-brand-accent/20"
      }`}
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border ${C.bodyXs} font-semibold ${badgeClass}`}
          >
            {PhoneStateIcon ? <PhoneStateIcon size={12} /> : <ChannelIcon size={12} />}
            {channelLabel}
          </span>
          <span className={`${C.bodyXs} ${C.color.mutedLight}`}>
            {formatDateTime(entry.created_at)}
          </span>
        </div>
        <span className={`${C.bodyXs} font-semibold ${inbound ? C.color.accent : C.color.muted}`}>
          {directionLabel}
        </span>
      </div>

      {entry.subject && (
        <p className={`${C.bodySm} font-semibold ${C.color.text}`}>{entry.subject}</p>
      )}

      {isPhone ? (
        <div className="flex items-start gap-3 flex-wrap">
          <p className={`${C.bodySm} ${C.color.text} flex-1 min-w-[140px]`}>
            {summaryText ? `📞 ${formatCallDuration(entry.call_duration)} · ${summaryText}` : fallbackBody}
          </p>
          {entry.media_url && (
            <a
              href={entry.media_url}
              target="_blank"
              rel="noreferrer"
              className={`inline-flex items-center gap-1 px-3 py-1 ${C.bodyXs} font-semibold ${C.button.ghost}`}
            >
              <Play size={12} />
              Запись
            </a>
          )}
        </div>
      ) : (
        fallbackBody && (
          <p className={`${C.bodySm} ${C.color.text} whitespace-pre-wrap break-words`}>
            {fallbackBody}
          </p>
        )
      )}

      {isPhone && entry.transcript && (
        <div>
          <button
            type="button"
            onClick={() => setTranscriptOpen((v) => !v)}
            className={`inline-flex items-center gap-1 ${C.bodyXs} ${C.color.muted} hover:${C.color.accent} transition-colors`}
          >
            {transcriptOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {transcriptOpen ? "Скрыть транскрипт" : "Показать транскрипт"}
          </button>
          {transcriptOpen && (
            <pre
              className={`mt-2 ${C.bodyXs} ${C.color.muted} whitespace-pre-wrap break-words font-sans bg-brand-panel/50 rounded-xl px-3 py-2 border border-brand-border`}
            >
              {entry.transcript}
            </pre>
          )}
        </div>
      )}

      {!isPhone && entry.sender_id && (
        <p className={`${C.bodyXs} ${C.color.mutedLight}`}>от {entry.sender_id}</p>
      )}
    </li>
  );
}

function ComposerHint({
  channel,
  links,
}: {
  channel: ComposerChannel;
  links: InboxFeedOut["channels_linked"];
}) {
  if (channel === "telegram") {
    const linked = links.telegram?.linked;
    if (!linked) {
      return (
        <p className={`${C.bodyXs} ${C.color.muted}`}>
          У лида не указан Telegram chat ID — добавьте его в профиле, чтобы написать через бота.
        </p>
      );
    }
  }
  return null;
}

function readSavedExtension(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(EXTENSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistExtension(value: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(EXTENSION_STORAGE_KEY, value);
  } catch {
    // ignore — localStorage may be unavailable in private mode
  }
}

export function InboxTab({ lead }: Props) {
  const inboxQuery = useLeadInbox(lead.id);
  const sendMutation = useLeadInboxSend(lead.id);
  const callMutation = useLeadInboxCall(lead.id);

  const [filter, setFilter] = useState<FilterKey>("all");
  const [composerChannel, setComposerChannel] = useState<ComposerChannel>("telegram");
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [callError, setCallError] = useState<string | null>(null);
  const [callToast, setCallToast] = useState<string | null>(null);

  const data = inboxQuery.data;
  const links = data?.channels_linked ?? {};

  const filtered = useMemo(() => {
    const messages = data?.messages ?? [];
    if (filter === "all") return messages;
    return messages.filter((m) => m.channel === filter);
  }, [data, filter]);

  const phoneLinked = !!links.phone?.linked;
  const tgLinked = !!links.telegram?.linked;

  const composerDisabled =
    sendMutation.isPending ||
    !draft.trim() ||
    (composerChannel === "telegram" && !tgLinked);

  async function handleSend() {
    setSendError(null);
    try {
      await sendMutation.mutateAsync({ channel: composerChannel, body: draft.trim() });
      setDraft("");
    } catch (err) {
      const detail =
        err instanceof ApiError && typeof err.body === "object" && err.body && "detail" in err.body
          ? String((err.body as { detail?: unknown }).detail ?? "")
          : "Не удалось отправить сообщение";
      setSendError(detail || "Не удалось отправить сообщение");
    }
  }

  async function handleCall() {
    setCallError(null);
    setCallToast(null);
    if (!phoneLinked) {
      setCallError("У лида не указан номер телефона.");
      return;
    }
    let ext = readSavedExtension();
    if (!ext) {
      const entered = typeof window !== "undefined"
        ? window.prompt("Ваш внутренний номер (extension):", "")
        : null;
      if (!entered) return;
      ext = entered.trim();
      if (!ext) return;
      persistExtension(ext);
    }
    try {
      await callMutation.mutateAsync({ from_extension: ext });
      setCallToast("Звоним… дождитесь поднятия трубки на вашем аппарате.");
    } catch (err) {
      const detail =
        err instanceof ApiError && typeof err.body === "object" && err.body && "detail" in err.body
          ? String((err.body as { detail?: unknown }).detail ?? "")
          : "Не удалось инициировать звонок";
      setCallError(detail || "Не удалось инициировать звонок");
    }
  }

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`px-3.5 py-1.5 ${C.bodyXs} font-semibold border rounded-full transition-colors ${
                active
                  ? "bg-brand-accent text-white border-brand-accent"
                  : "bg-white text-brand-muted-strong border-brand-border hover:border-brand-accent/40"
              }`}
            >
              {f.label}
            </button>
          );
        })}
        <button
          type="button"
          onClick={handleCall}
          disabled={callMutation.isPending}
          className={`ml-auto inline-flex items-center gap-1.5 px-3.5 py-1.5 ${C.bodyXs} font-semibold ${C.button.primary} disabled:opacity-60`}
        >
          {callMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Phone size={12} />}
          Позвонить
        </button>
      </div>

      {callError && (
        <p className={`${C.bodyXs} text-rose-600`}>{callError}</p>
      )}
      {callToast && (
        <p className={`${C.bodyXs} ${C.color.accent}`}>{callToast}</p>
      )}

      {/* Feed */}
      {inboxQuery.isLoading ? (
        <div className={`py-8 text-center ${C.bodySm} ${C.color.muted}`}>
          <Loader2 className="inline-block animate-spin mr-2" size={14} />
          Загрузка переписки…
        </div>
      ) : inboxQuery.isError ? (
        <p className={`${C.bodySm} text-rose-600 py-4 text-center`}>
          Не удалось загрузить переписку.
        </p>
      ) : filtered.length === 0 ? (
        <p className={`${C.bodySm} ${C.color.muted} italic py-8 text-center`}>
          {filter === "all"
            ? "Сообщений по этому лиду пока нет."
            : filter === "email"
              ? "Переписка по Gmail сейчас доступна в табе «Активность»."
              : `Сообщений в канале «${FILTERS.find((f) => f.key === filter)?.label}» нет.`}
        </p>
      ) : (
        <ul className="space-y-2.5">
          {filtered.map((m) => (
            <MessageItem key={m.id} entry={m} />
          ))}
        </ul>
      )}

      {/* Composer */}
      <div className="border-t border-brand-border pt-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`${C.bodyXs} ${C.color.muted}`}>Ответить в:</span>
          <button
            type="button"
            onClick={() => setComposerChannel("telegram")}
            className={`inline-flex items-center gap-1.5 px-3 py-1 ${C.bodyXs} font-semibold border rounded-full transition-colors ${
              composerChannel === "telegram"
                ? "bg-brand-accent text-white border-brand-accent"
                : "bg-white text-brand-muted-strong border-brand-border"
            }`}
          >
            <MessageCircle size={12} />
            Telegram
          </button>
          <span className={`${C.bodyXs} ${C.color.mutedLight}`} title="Email-отправка появится в G5">
            · Email/MAX позже
          </span>
        </div>

        <ComposerHint channel={composerChannel} links={links} />

        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          placeholder="Написать сообщение..."
          className={`w-full bg-white border border-brand-border rounded-2xl px-4 py-2.5 ${C.bodySm} ${C.color.text} outline-none focus:border-brand-accent transition-colors resize-y`}
        />

        {sendError && <p className={`${C.bodyXs} text-rose-600`}>{sendError}</p>}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={handleSend}
            disabled={composerDisabled}
            className={`inline-flex items-center gap-1.5 px-4 py-2 ${C.bodySm} font-semibold ${C.button.primary} disabled:opacity-50`}
          >
            {sendMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            Отправить
          </button>
        </div>
      </div>
    </div>
  );
}
