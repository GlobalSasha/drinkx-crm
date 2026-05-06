"use client";
import { use } from "react";
import { LeadCard } from "@/components/lead-card/LeadCard";

export default function LeadCardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <LeadCard leadId={id} />;
}
