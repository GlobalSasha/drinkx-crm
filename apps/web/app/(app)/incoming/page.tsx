"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, CheckCheck, Inbox, Loader2 } from "lucide-react";
import { clsx } from "clsx";

import { T, C } from "@/lib/design-system";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <div className={pageContainerVariants({ width: "wide" })}>
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
      <div className="bg-white border border-brand-border rounded-[2rem] p-4 sm:p-5 mb-4 flex flex-wrap items-center gap-2">
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

function Row({ item, onOpenLead }: { item: InboxItemOut; onOpenLead: () => void }) {
  const st = statusLabel(item);
  const title = item.company_name || "Без названия";
  return (
    <div
      onClick={onOpenLead}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onOpenLead();
      }}
      className="relative rounded-[2rem] border border-brand-border bg-white px-4 py-3.5 pl-5 cursor-pointer transition-colors hover:border-brand-muted"
    >
      {item.is_new && (
        <span className="absolute left-2 top-5 w-2 h-2 rounded-full bg-brand-accent" />
      )}
      <div className="flex items-center gap-2">
        <span className="text-[15px] font-bold text-brand-primary truncate">{title}</span>
        <span className="ml-auto text-xs text-brand-muted whitespace-nowrap">
          {relativeTime(item.created_at)}
        </span>
      </div>

      <div className="flex gap-3.5 mt-1 text-sm text-brand-muted flex-wrap">
        {item.phone && <span className="text-brand-muted-strong font-medium">{item.phone}</span>}
        {item.email && <span>{item.email}</span>}
      </div>

      {item.snippet && (
        <p className="text-sm text-brand-muted-strong mt-2 leading-snug line-clamp-2">
          {item.snippet}
        </p>
      )}

      <div className="flex items-center gap-2 mt-2.5 flex-wrap">
        <span className={`${T.mono} text-[10px] uppercase tracking-wider px-2 py-1 rounded-md bg-brand-bg text-brand-muted`}>
          {item.channel}
        </span>
        <StatusPill st={st} />
        <span className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-brand-accent">
          Открыть лида <ArrowRight size={12} />
        </span>
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
    <span className={clsx("text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-md", cls)}>
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
