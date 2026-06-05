"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, CheckCheck, Inbox, Loader2 } from "lucide-react";
import { clsx } from "clsx";

import { T } from "@/lib/design-system";
import { useForms } from "@/lib/hooks/use-forms";
import { useIncoming, useMarkIncomingSeen } from "@/lib/hooks/use-incoming";
import { relativeTime } from "@/lib/relative-time";
import type { InboxItemOut } from "@/lib/types";

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
  const [selectedId, setSelectedId] = useState<string | null>(null);

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

  // Keep a selection in sync with the list.
  const selected = items.find((i) => i.submission_id === selectedId) ?? items[0] ?? null;

  function openLead(it: InboxItemOut | null) {
    if (it?.lead_id) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      router.push(`/leads/${it.lead_id}` as any);
    }
  }

  return (
    <>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b border-black/5 px-6 py-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-baseline gap-2.5">
            <h1 className="type-card-title">Входящие заявки</h1>
            {newCount > 0 && (
              <span className="bg-brand-accent/10 text-brand-accent font-semibold text-xs px-2 py-0.5 rounded-md">
                {newCount} новых
              </span>
            )}
            <span className="text-muted-3 text-xs font-mono tabular-nums">
              всего {total}
            </span>
          </div>
          <button
            onClick={() => markSeen.mutate()}
            disabled={markSeen.isPending}
            className="inline-flex items-center gap-1.5 border border-black/10 bg-white text-muted rounded-pill px-3.5 py-2 text-sm font-semibold hover:text-ink hover:border-black/20 disabled:opacity-40 transition-colors"
          >
            <CheckCheck size={14} />
            Отметить все прочитанными
          </button>
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-2 mt-3 flex-wrap">
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
      </div>

      <div className="flex min-h-0 flex-1">
        {/* List */}
        <div className="flex-1 px-6 py-4 overflow-y-auto">
          {inboxQuery.isLoading && (
            <div className="flex justify-center py-12">
              <Loader2 size={20} className="animate-spin text-muted-2" />
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
              <Row
                key={it.submission_id}
                item={it}
                selected={selected?.submission_id === it.submission_id}
                onSelect={() => setSelectedId(it.submission_id)}
                onOpenLead={() => openLead(it)}
              />
            ))}
          </div>
        </div>

        {/* Detail preview — hidden on small screens */}
        {selected && (
          <aside className="hidden lg:block w-[360px] flex-none border-l border-black/5 bg-white px-5 py-5 overflow-y-auto">
            <Detail item={selected} onOpenLead={() => openLead(selected)} />
          </aside>
        )}
      </div>
    </>
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
        "text-sm font-semibold px-3.5 py-1.5 rounded-pill border transition-colors",
        active
          ? "bg-ink text-white border-ink"
          : "bg-white text-muted border-black/10 hover:text-ink hover:border-black/20",
      )}
    >
      {children}
    </button>
  );
}

function Row({
  item,
  selected,
  onSelect,
  onOpenLead,
}: {
  item: InboxItemOut;
  selected: boolean;
  onSelect: () => void;
  onOpenLead: () => void;
}) {
  const st = statusLabel(item);
  const title = item.company_name || "Без названия";
  return (
    <div
      onClick={onSelect}
      className={clsx(
        "relative rounded-2xl border bg-white px-4 py-3.5 pl-5 cursor-pointer transition-all",
        selected
          ? "border-brand-accent ring-2 ring-brand-accent/15"
          : "border-black/5 hover:border-black/15",
      )}
    >
      {item.is_new && (
        <span className="absolute left-2 top-5 w-2 h-2 rounded-full bg-brand-accent" />
      )}
      <div className="flex items-center gap-2">
        <span className="text-[15px] font-bold text-ink truncate">{title}</span>
        <span className="ml-auto text-xs text-muted-3 whitespace-nowrap">
          {relativeTime(item.created_at)}
        </span>
      </div>

      <div className="flex gap-3.5 mt-1 text-sm text-muted flex-wrap">
        {item.phone && <span className="text-ink/70 font-medium">{item.phone}</span>}
        {item.email && <span>{item.email}</span>}
      </div>

      {item.snippet && (
        <p className="text-sm text-ink/70 mt-2 leading-snug line-clamp-2">
          {item.snippet}
        </p>
      )}

      <div className="flex items-center gap-2 mt-2.5 flex-wrap">
        <span className={`${T.mono} text-[10px] uppercase tracking-wider px-2 py-1 rounded-md bg-canvas text-muted-2`}>
          {item.channel}
        </span>
        <StatusPill st={st} />
        <button
          onClick={(e) => {
            e.stopPropagation();
            onOpenLead();
          }}
          className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-brand-accent hover:underline"
        >
          Открыть лида <ArrowRight size={12} />
        </button>
      </div>
    </div>
  );
}

function StatusPill({ st }: { st: ReturnType<typeof statusLabel> }) {
  const cls =
    st.tone === "new"
      ? "bg-brand-accent/10 text-brand-accent"
      : st.tone === "assigned"
        ? "bg-canvas-2 text-muted"
        : "bg-canvas text-muted-2";
  return (
    <span className={clsx("text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-md", cls)}>
      {st.text}
    </span>
  );
}

function Detail({ item, onOpenLead }: { item: InboxItemOut; onOpenLead: () => void }) {
  const utm = item.utm_json
    ? Object.entries(item.utm_json)
        .map(([k, v]) => `${k}=${v}`)
        .join(" · ")
    : null;
  return (
    <div>
      <div className="text-[17px] font-bold text-ink tracking-tight">
        {item.company_name || "Без названия"}
      </div>
      <div className={`${T.mono} text-[11px] text-muted-2 mt-1.5 mb-5`}>
        {item.channel} · {relativeTime(item.created_at)}
      </div>

      <dl className="flex flex-col gap-3.5 mb-5">
        <Field k="Телефон" v={item.phone} />
        <Field k="Email" v={item.email} />
        <Field k="Сообщение" v={item.snippet} multiline />
        <Field k="Источник (домен)" v={item.source_domain} />
        <Field k="UTM" v={utm} mono />
      </dl>

      <button
        onClick={onOpenLead}
        disabled={!item.lead_id}
        className="block w-full text-center bg-ink text-white font-semibold text-sm py-3 rounded-pill hover:bg-ink/90 disabled:opacity-40 transition-colors"
      >
        Открыть карточку лида →
      </button>
    </div>
  );
}

function Field({
  k,
  v,
  multiline,
  mono,
}: {
  k: string;
  v: string | null | undefined;
  multiline?: boolean;
  mono?: boolean;
}) {
  if (!v) return null;
  return (
    <div>
      <dt className={`${T.mono} text-[9.5px] uppercase tracking-wider text-muted-2`}>{k}</dt>
      <dd
        className={clsx(
          "mt-1 text-ink",
          multiline ? "text-sm font-normal leading-relaxed text-ink/80" : "text-sm font-semibold",
          mono && "font-mono text-xs",
        )}
      >
        {v}
      </dd>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-12 h-12 rounded-full bg-canvas flex items-center justify-center mb-3">
        <Inbox size={22} className="text-muted-3" />
      </div>
      <div className="text-sm font-bold text-ink">Заявок пока нет</div>
      <p className="text-sm text-muted-2 mt-1 max-w-[24rem]">
        Здесь будут появляться заявки, отправленные через формы на сайтах.
      </p>
    </div>
  );
}
