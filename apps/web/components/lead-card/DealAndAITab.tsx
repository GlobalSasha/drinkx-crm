"use client";
import type { LeadOut } from "@/lib/types";
import { SourceSection } from "./SourceSection";
import { LeadInfoBlock } from "./LeadInfoBlock";

interface Props {
  lead: LeadOut;
}

export function DealAndAITab({ lead }: Props) {
  return (
    <div className="space-y-4">
      {/* Editable info + property table + collapsible AI Бриф, one card. */}
      <LeadInfoBlock lead={lead} />

      {/* Источник (only for form-sourced leads) */}
      <SourceSection lead={lead} />
    </div>
  );
}
