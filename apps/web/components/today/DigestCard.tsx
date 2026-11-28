"use client";
// «Сводка за 5 дней» on the head/admin /today: what clients said in manager
// comments, retold by the AI worker overnight, and the leads that came in.
// The CRM keeps a line only if it names leads with comments in the period, so
// every line opens the lead it is about. New leads come from the base, no AI.
// Data: GET /company/digest.
import { useState, type ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ChevronRight,
  Hourglass,
  MessageSquareWarning,
  TrendingUp,
  UserPlus,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { C } from "@/lib/design-system";
import { useCompanyDigest } from "@/lib/hooks/use-company";
import type { CompanyDigest, DigestItem } from "@/lib/types";

const SECTION_ICON: Record<string, ReactNode> = {
  progress: <TrendingUp size={18} aria-hidden />,
  objections: <MessageSquareWarning size={18} aria-hidden />,
  postponed: <Hourglass size={18} aria-hidden />,
  attention: <AlertTriangle size={18} aria-hidden />,
};

// Good news green, objections red, delays amber, «look at this» blue.
const SECTION_COLOR: Record<string, string> = {
  progress: "text-success",
  objections: "text-rose",
  postponed: "text-warning",
  attention: "text-info",
};

const SECTION_TITLE = "inline-flex items-center gap-2 type-button mb-2";

/** Client label for the left column. Older digests had it glued to the
 *  front of the text («Гуру кофе (СПб): …») — split it off there. */
export function splitClient(item: DigestItem): { client: string; text: string } {
  if (item.client) return { client: item.client, text: item.text };
  const cut = item.text.indexOf(": ");
  if (cut > 0 && cut <= 60) {
    return { client: item.text.slice(0, cut), text: item.text.slice(cut + 2) };
  }
  return { client: item.leads[0]?.company_name ?? "", text: item.text };
}

const NEW_LEADS_SHOWN = 8;

const dayMonth = (iso: string) =>
  new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });

export function periodLabel(fromIso: string, toIso: string): string {
  const from = new Date(fromIso);
  const to = new Date(toIso);
  if (from.getMonth() === to.getMonth()) {
    return `${from.getDate()}–${dayMonth(toIso)}`;
  }
  return `${dayMonth(fromIso)} – ${dayMonth(toIso)}`;
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export function DigestCard() {
  const { data, isLoading, isError } = useCompanyDigest();

  return (
    <Card className="mb-5">
      <div className="mb-4">
        <h3 className="type-card-title text-brand-primary">Сводка за 5 дней</h3>
        {data?.digest && (
          <p className="type-hint not-italic text-brand-muted">
            {periodLabel(data.digest.period_from, data.digest.period_to)} ·{" "}
            {data.digest.comments}{" "}
            {plural(data.digest.comments, "комментарий", "комментария", "комментариев")} по{" "}
            {data.digest.leads} {plural(data.digest.leads, "лиду", "лидам", "лидам")}
          </p>
        )}
      </div>

      {isError ? (
        <p className="type-body text-rose py-6 text-center">Не удалось загрузить — обновите страницу.</p>
      ) : isLoading || !data ? (
        <div className="h-24 rounded-lg bg-brand-panel animate-pulse" aria-hidden />
      ) : (
        <Body data={data} />
      )}
    </Card>
  );
}

function Body({ data }: { data: CompanyDigest }) {
  const sections = data.digest?.sections ?? [];
  return (
    <div className="space-y-6">
      {data.stale && (
        <p className="flex items-start gap-2 rounded-lg bg-warning/10 px-4 py-3 type-body text-brand-primary">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" aria-hidden />
          {data.digest
            ? `Сводка не обновлялась с ${shortDate(data.digest.created_at)}: ночной разбор не прошёл.`
            : "Сводки ещё нет: она появится после ночного разбора комментариев."}
        </p>
      )}
      {data.digest && sections.length === 0 && (
        <p className="type-body text-brand-muted">В комментариях за эти дни ничего важного не нашлось.</p>
      )}
      {sections.map((s) => (
        <section key={s.key} aria-label={s.title}>
          <h4 className={`${SECTION_TITLE} ${SECTION_COLOR[s.key] ?? "text-brand-primary"}`}>
            {SECTION_ICON[s.key]}
            {s.title}
          </h4>
          <ul>
            {s.items.map((it, i) => (
              <DigestLine key={i} item={it} />
            ))}
          </ul>
        </section>
      ))}
      <NewLeads data={data} />
    </div>
  );
}

// One row: client on the left, what happened on the right, the same grid in
// every section. The whole row opens the lead card.
const ROW_GRID =
  "grid grid-cols-1 sm:grid-cols-[200px_minmax(0,1fr)_16px] gap-x-4 gap-y-1 py-2 px-2 -mx-2 rounded-md";

function DigestLine({ item }: { item: DigestItem }) {
  const { client, text } = splitClient(item);
  const [first, ...more] = item.leads;
  return (
    <li className="border-t border-brand-border first:border-t-0">
      <Link
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        href={`/leads/${first.id}` as any}
        title={`Открыть карточку: ${first.company_name}`}
        className={`group ${ROW_GRID} items-baseline hover:bg-brand-bg transition-colors ${C.focusRing}`}
      >
        <span className="type-body font-medium text-brand-primary group-hover:text-brand-accent-text">
          {client}
        </span>
        <span className="type-body text-brand-primary">{text}</span>
        <ChevronRight
          size={16}
          className="hidden sm:block self-center text-brand-muted group-hover:text-brand-accent-text"
          aria-hidden
        />
      </Link>
      {more.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-[200px_minmax(0,1fr)] gap-x-4 px-2 -mx-2 pb-2">
        <span className="hidden sm:block" aria-hidden />
        <p className="type-hint not-italic text-brand-muted">
          Ещё:{" "}
          {more.map((l, i) => (
            <span key={l.id}>
              {i > 0 && ", "}
              <Link
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={`/leads/${l.id}` as any}
                className={`text-brand-accent-text hover:underline rounded-md ${C.focusRing}`}
              >
                {l.company_name}
              </Link>
            </span>
          ))}
        </p>
        </div>
      )}
    </li>
  );
}

function NewLeads({ data }: { data: CompanyDigest }) {
  const [all, setAll] = useState(false);
  const leads = data.new_leads;
  const shown = all ? leads : leads.slice(0, NEW_LEADS_SHOWN);
  return (
    <section aria-label="Новые лиды">
      <h4 className={`${SECTION_TITLE} text-brand-primary`}>
        <UserPlus size={18} aria-hidden />
        Новые лиды · {leads.length}
      </h4>
      {leads.length === 0 ? (
        <p className="type-body text-brand-muted">За 5 дней новых лидов не было.</p>
      ) : (
        <ul>
          {shown.map((l) => (
            <li key={l.id} className="border-t border-brand-border first:border-t-0">
              <Link
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={`/leads/${l.id}` as any}
                className={`group ${ROW_GRID} items-baseline hover:bg-brand-bg transition-colors ${C.focusRing}`}
              >
                <span className="type-body font-medium text-brand-primary group-hover:text-brand-accent-text">
                  {l.company_name}
                </span>
                <span className="type-body text-brand-muted">
                  {[shortDate(l.created_at), l.city, l.source, l.manager].filter(Boolean).join(" · ")}
                </span>
                <ChevronRight
                  size={16}
                  className="hidden sm:block self-center text-brand-muted group-hover:text-brand-accent-text"
                  aria-hidden
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {leads.length > NEW_LEADS_SHOWN && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className={`mt-2 py-1 coarse:py-2 type-caption text-brand-accent-text hover:underline rounded-full ${C.focusRing}`}
        >
          {all ? "Свернуть" : `Все новые лиды (${leads.length})`}
        </button>
      )}
    </section>
  );
}
