import { AlertCircle, CheckCircle2, Clock, MinusCircle } from "lucide-react";

import type { AutomationRunStatus } from "@/lib/types";

export function StatusIcon({ status }: { status: AutomationRunStatus }) {
  if (status === "success")
    return <CheckCircle2 size={11} className="text-success" />;
  if (status === "skipped")
    return <MinusCircle size={11} className="text-brand-muted" />;
  if (status === "failed")
    return <AlertCircle size={11} className="text-rose" />;
  return <Clock size={11} className="text-brand-muted" />;
}
