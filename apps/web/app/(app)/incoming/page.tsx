"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, CheckCheck, Check, Copy, Inbox, Loader2, Mail, Phone } from "lucide-react";
import { clsx } from "clsx";

import { T, C } from "@/lib/design-system";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useForms } from "@/lib/hooks/use-forms";
import { useIncoming, useMarkIncomingSeen } from "@/lib/hooks/use-incoming";
import type { InboxItemOut } from "@/lib/types";

/**
 * Arrival timestamp for the left gutter. Time is the anchor (scannable,
 * tabular); the date is a smart label — «Сегодня» / «Вчера» / «21 июн.»,
 * falling back to a numeric `дд.мм.гг` for prior years so it stays compact.
 */
function formatArrival(iso: string): { time: string; date: string; full: string } {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { time: "—", date: "", full: "" };
  const now = new Date();
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const startOfDay = (x: Date) =>
    new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const dayDiff = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000);

  let date: string;
  if (dayDiff === 0) date = "Сегодня";
  else if (dayDiff === 1) date = "Вчера";
  else if (d.getFullYear() === now.getFullYear())
    date = d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
  else date = d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" });

  const full = d.toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return { time, date, full };
}

function statusLabel(it: InboxItemOut): { text: string; tone: "new" | "assigned" | "muted" } {
  if (it.is_new && (!it.assignment_status || it.assignment_status === "pool")) {
    return { text: "Новая", tone: "new" };
  }
  if (it.assignee_name) {
    return { text: `Назначен · ${it.assignee_name}`, tone: "assigned" };
  }
  if (it.assignment_status === "pool") return { text: "В пуле", tone: "muted" };
  return { text: "Просмотрена", tone: "muted" };
}

export default function IncomingPage() {
  const router = useRouter();
  const [channel, setChannel] = useState<string | null>(null); // form_id
  const [unseenOnly, setUnseenOnly] = useState(false);

  const formsQuery = useForms();
  const inboxQuery = useIncoming({ formId: channel, unseenOnly });
  const markSeen = useMarkIncomingSeen();

  const items = useMemo(() => inboxQuery.data?.items ?? [], [inboxQuery.data]);
  const newCount = inboxQuery.data?.new_count ?? 0;
  const total = inboxQuery.data?.total ?? 0;
  const forms = formsQuery.data?.items ?? [];

  // Mark everything seen once, on first successful load — like opening
  // your email inbox clears the unread count.
  const markedRef = useRef(false);
  useEffect(() => {
    if (!markedRef.current && inboxQuery.isSuccess) {
      markedRef.current = true;
      markSeen.mutate();
    }
  }, [inboxQuery.isSuccess, markSeen]);

  function openLead(it: InboxItemOut) {
    if (it.lead_id) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      router.push(`/leads/${it.lead_id}` as any);
    }
  }

  return (
    <div className={pageContainerVariants({ surface: "data" })}>
      <PageHeader
        icon={<Inbox size={20} />}
        title="Входящие заявки"
        actions={
          <>
            {newCount > 0 && (
              <span className="bg-brand-accent/10 text-brand-accent font-semibold text-xs px-2 py-0.5 rounded-md">
                {newCount} новых
              </span>
            )}
            <span className="text-brand-muted text-xs font-mono tabular-nums">
              всего {total}
            </span>
            <button
              onClick={() => markSeen.mutate()}
              disabled={markSeen.isPending}
              className={`${C.button.ghost} inline-flex items-center gap-1.5 px-3.5 py-1.5 text-sm font-semibold disabled:opacity-40`}
            >
              <CheckCheck size={14} />
              Отметить все прочитанными
            </button>
          </>
        }
      />

      {/* Filter row */}
      <div className="bg-white border border-brand-border rounded-card p-4 sm:p-5 mb-4 flex flex-wrap items-center gap-2">
        <Chip active={channel === null} onClick={() => setChannel(null)}>
          Все
        </Chip>
        {forms.map((f) => (
          <Chip key={f.id} active={channel === f.id} onClick={() => setChannel(f.id)}>
            {f.source_label || f.name}
          </Chip>
        ))}
        <span className="flex-1" />
        <Chip active={unseenOnly} onClick={() => setUnseenOnly((v) => !v)}>
          Только новые
        </Chip>
      </div>

      {/* List */}
      <div>
        {inboxQuery.isLoading && (
          <div className="flex justify-center py-12">
            <Loader2 size={20} className="animate-spin text-brand-muted" />
          </div>
        )}

        {inboxQuery.isError && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-rose/10 text-rose text-sm">
            <AlertCircle size={14} />
            Не удалось загрузить заявки.
          </div>
        )}

        {!inboxQuery.isLoading && !inboxQuery.isError && items.length === 0 && (
          <EmptyState />
        )}

        <div className="flex flex-col gap-2.5">
          {items.map((it) => (
            <Row key={it.submission_id} item={it} onOpenLead={() => openLead(it)} />
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "px-3 py-1.5 rounded-full type-caption font-semibold transition-colors",
        active
          ? "bg-brand-accent text-white"
          : "bg-brand-panel text-brand-muted-strong hover:bg-brand-border",
      )}
    >
      {children}
    </button>
  );
}

function ContactChip({
  href,
  icon,
  label,
  copyText,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  copyText: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <span className="inline-flex items-center rounded-full bg-brand-bg border border-brand-border overflow-hidden">
      <a
        href={href}
        onClick={(e) => e.stopPropagation()}
        className="inline-flex items-center gap-1.5 px-3 py-1 max-w-[220px] type-caption font-medium text-brand-muted-strong hover:text-brand-accent transition-colors"
      >
        {icon}
        <span className="truncate">{label}</span>
      </a>
      <button
        type="button"
        aria-label="Копировать"
        onClick={(e) => {
          e.stopPropagation();
          void navigator.clipboard?.writeText(copyText);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="px-2 py-1 text-brand-muted hover:text-brand-accent border-l border-brand-border transition-colors"
      >
        {copied ? <Check size={11} /> : <Copy size={11} />}
      </button>
    </span>
  );
}

function Row({ item, onOpenLead }: { item: InboxItemOut; onOpenLead: () => void }) {
  const st = statusLabel(item);
  const company = item.company_name || "Без названия";
  const arr = formatArrival(item.created_at);
  return (
    <div
      onClick={onOpenLead}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onOpenLead();
      }}
      className="flex gap-3 sm:gap-4 rounded-card border border-brand-border bg-white px-4 py-3.5 cursor-pointer transition-colors hover:border-brand-muted"
    >
      {/* Arrival — left gutter; time is the anchor, dates line up top-to-bottom */}
      <div
        title={arr.full}
        className="flex shrink-0 w-16 flex-col items-start border-r border-brand-border pr-3"
      >
        <span
          className={clsx(
            "text-base font-bold tabular-nums leading-tight",
            item.is_new ? "text-brand-accent" : "text-brand-primary",
          )}
        >
          {arr.time}
        </span>
        <span className="mt-1 whitespace-nowrap text-2xs text-brand-muted">{arr.date}</span>
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        {/* Who */}
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-brand-primary truncate">
            {item.contact_name || company}
          </span>
          {item.contact_name && (
            <span className="text-sm text-brand-muted truncate">{company}</span>
          )}
        </div>

        {/* Clickable contacts */}
        {(item.phone || item.email) && (
          <div className="flex gap-2 mt-2 flex-wrap">
            {item.phone && (
              <ContactChip
                href={`tel:${item.phone}`}
                icon={<Phone size={12} />}
                label={item.phone}
                copyText={item.phone}
              />
            )}
            {item.email && (
              <ContactChip
                href={`mailto:${item.email}`}
                icon={<Mail size={12} />}
                label={item.email}
                copyText={item.email}
              />
            )}
          </div>
        )}

        {/* Question / structured summary */}
        {item.question ? (
          <p className="text-sm text-brand-muted-strong mt-2 leading-snug line-clamp-2">
            <span className="font-semibold">Вопрос клиента:</span> {item.question}
          </p>
        ) : item.summary ? (
          <p className="text-sm text-brand-muted mt-2 leading-snug line-clamp-2">
            <span className="font-semibold">Из заявки:</span> {item.summary}
          </p>
        ) : null}

        {/* Source + status */}
        <div className="flex items-center gap-2 mt-2.5 flex-wrap">
          <span className={`${T.mono} text-2xs uppercase tracking-wider px-2 py-1 rounded-md bg-brand-bg text-brand-muted`}>
            {item.channel}
          </span>
          {item.source_domain && (
            <span className="text-xs text-brand-muted">{item.source_domain}</span>
          )}
          <StatusPill st={st} />
          <span className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-brand-accent">
            Открыть лида <ArrowRight size={12} />
          </span>
        </div>
      </div>
    </div>
  );
}

function StatusPill({ st }: { st: ReturnType<typeof statusLabel> }) {
  const cls =
    st.tone === "new"
      ? "bg-brand-accent/10 text-brand-accent"
      : st.tone === "assigned"
        ? "bg-brand-panel text-brand-muted-strong"
        : "bg-brand-bg text-brand-muted";
  return (
    <span className={clsx("text-2xs font-semibold uppercase tracking-wider px-2 py-1 rounded-md", cls)}>
      {st.text}
    </span>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-12 h-12 rounded-full bg-brand-bg flex items-center justify-center mb-3">
        <Inbox size={22} className="text-brand-muted" />
      </div>
      <div className="text-sm font-bold text-brand-primary">Заявок пока нет</div>
      <p className="text-sm text-brand-muted mt-1 max-w-[24rem]">
        Здесь будут появляться заявки, отправленные через формы на сайтах.
      </p>
    </div>
  );
}
