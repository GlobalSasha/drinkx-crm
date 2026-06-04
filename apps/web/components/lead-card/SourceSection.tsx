"use client";

import { useState } from "react";
import { ChevronDown, Globe, Link as LinkIcon } from "lucide-react";
import Link from "next/link";
import type { LeadOut } from "@/lib/types";
import { useFeed } from "@/lib/hooks/use-feed";
import { C } from "@/lib/design-system";

interface Props {
  lead: LeadOut;
}

// Render only when the lead was sourced from a form. The chip on the
// header (in LeadCard.tsx) handles the always-visible signal; this
// section is the structured drill-down inside DealAndAITab.
export function SourceSection({ lead }: Props) {
  const isFormSourced =
    typeof lead.source === "string" && lead.source.startsWith("form:");
  if (!isFormSourced) return null;

  return (
    <section className="bg-white rounded-2xl border border-brand-border p-5">
      <header className="flex items-center gap-2 mb-4">
        <Globe size={16} className="text-brand-accent" />
        <h2 className={`type-card-title font-bold ${C.color.text}`}>Источник</h2>
      </header>
      <SourceBody lead={lead} />
    </section>
  );
}

function SourceBody({ lead }: { lead: LeadOut }) {
  const formName = lead.source_form_name;
  const formId = lead.source_form_id;
  const utm = lead.latest_utm ?? {};
  const utmEntries = Object.entries(utm).filter(([, v]) => v);

  // Pull source_domain + raw_payload from the latest form_submission
  // Activity. We read the feed instead of duplicating server-side
  // because the feed is already in TanStack Query cache by the time
  // the user opens this tab.
  const feed = useFeed(lead.id);
  const latestSubmission = feed.data?.pages
    ?.flatMap((p) => p.items)
    ?.find((it) => it.type === "form_submission");
  const sourceDomain =
    (latestSubmission?.payload_json?.source_domain as string | undefined) || null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rawPayload = latestSubmission?.payload_json as Record<string, any> | undefined;

  return (
    <ul className="space-y-3 type-caption">
      <li className="flex items-start gap-3">
        <LinkIcon size={14} className="mt-0.5 text-brand-muted shrink-0" />
        <div className="flex-1 min-w-0">
          {formId && formName ? (
            <Link
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              href={`/leads-pool?form_id=${formId}` as any}
              className={`${C.color.accent} hover:underline`}
            >
              {formName}
            </Link>
          ) : (
            <span className={C.color.muted}>Форма удалена</span>
          )}
          {sourceDomain && (
            <p className={`${C.color.mutedLight} mt-0.5 break-all`}>
              {sourceDomain}
            </p>
          )}
        </div>
      </li>

      {utmEntries.length > 0 && (
        <li className="border-t border-brand-border pt-3">
          <p className={`${C.color.mutedLight} uppercase tracking-wide text-2xs mb-2`}>
            UTM-параметры
          </p>
          <dl className="grid grid-cols-[120px_1fr] gap-y-1 gap-x-3 font-mono text-xs">
            {utmEntries.map(([k, v]) => (
              <UtmRow key={k} k={k} v={String(v)} />
            ))}
          </dl>
        </li>
      )}

      {rawPayload && (
        <li className="border-t border-brand-border pt-3">
          <RawPayloadDisclosure payload={rawPayload} />
        </li>
      )}
    </ul>
  );
}

function UtmRow({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt className="text-brand-muted">{k}</dt>
      <dd className="text-brand-primary">{v}</dd>
    </>
  );
}

function RawPayloadDisclosure({ payload }: { payload: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className="type-caption"
    >
      <summary className="cursor-pointer text-brand-muted inline-flex items-center gap-1 select-none">
        <ChevronDown
          size={12}
          className={`transition-transform ${open ? "rotate-0" : "-rotate-90"}`}
        />
        Raw payload
      </summary>
      <pre className="mt-2 p-2 bg-brand-panel rounded-md overflow-x-auto text-2xs font-mono">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
