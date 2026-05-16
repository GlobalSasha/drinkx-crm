"use client";

import {
  ArrowRightLeft,
  ClipboardList,
  Sparkles,
  User,
  Settings,
} from "lucide-react";
import type { FeedItemOut } from "@/lib/types";
import { formatTimeShort } from "./_time";

interface Props {
  item: FeedItemOut;
}

/**
 * Compact, muted row for auto-generated events. No author avatar —
 * the icon carries the meaning and the row blends into the feed.
 */
export function FeedItemSystem({ item }: Props) {
  const { icon, text } = render(item);
  return (
    <div className="flex items-center gap-2 type-caption text-brand-muted py-1.5">
      <span className="shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full bg-brand-bg">
        {icon}
      </span>
      <span className="flex-1 min-w-0 truncate">{text}</span>
      <span className="shrink-0 font-mono text-[10px] text-brand-muted">
        {formatTimeShort(item.created_at)}
      </span>
    </div>
  );
}

function render(item: FeedItemOut): { icon: React.ReactNode; text: string } {
  switch (item.type) {
    case "stage_change": {
      const from = (item.payload_json?.from_stage_name as string | null | undefined) || "—";
      const to = (item.payload_json?.to_stage_name as string | null | undefined) || "—";
      return {
        icon: <ArrowRightLeft size={11} />,
        text: `Стадия изменена: ${from} → ${to}`,
      };
    }
    case "lead_assigned":
      return {
        icon: <User size={11} />,
        text: "Лид взят в работу",
      };
    case "enrichment_done":
      return {
        icon: <Sparkles size={11} />,
        text: "Обогащение AI завершено",
      };
    case "form_submission": {
      const form = item.payload_json?.form_name as string | undefined;
      return {
        icon: <ClipboardList size={11} />,
        text: form ? `Заявка с формы: ${form}` : "Заявка с формы",
      };
    }
    default:
      return {
        icon: <Settings size={11} />,
        text: item.body || item.type,
      };
  }
}
