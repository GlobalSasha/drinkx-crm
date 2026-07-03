import { AlertCircle, CheckCircle2, Clock, MinusCircle } from "lucide-react";

import type { AutomationStepRunStatus } from "@/lib/types";

export function StepStatusIcon({ status }: { status: AutomationStepRunStatus }) {
  if (status === "success")
    return <CheckCircle2 size={10} className="text-success" />;
  if (status === "skipped")
    return <MinusCircle size={10} className="text-brand-muted" />;
  if (status === "failed")
    return <AlertCircle size={10} className="text-rose" />;
  return <Clock size={10} className="text-brand-muted" />;
}
