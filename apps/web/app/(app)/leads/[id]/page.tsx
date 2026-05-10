"use client";
import { Suspense, use } from "react";
import { LeadCard } from "@/components/lead-card/LeadCard";

// `LeadCard` reads `?tab=` via `useSearchParams`, which forces this
// route out of static rendering unless wrapped in Suspense.
export default function LeadCardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <Suspense fallback={null}>
      <LeadCard leadId={id} />
    </Suspense>
  );
}
