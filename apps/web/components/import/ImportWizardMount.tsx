"use client";

import { ImportWizard } from "@/components/import/ImportWizard";
import { usePipelineStore } from "@/lib/store/pipeline-store";

/**
 * Single-mount wrapper for the global ImportWizard. Lives in the
 * `(app)` layout so any page can call `openImportWizard()` from the
 * pipeline-store and have the modal appear — including the AI
 * bulk-update flow on /leads-pool which hands off to the wizard for
 * the upload step.
 */
export function ImportWizardMount() {
  const { importWizardOpen, closeImportWizard } = usePipelineStore();
  return <ImportWizard open={importWizardOpen} onClose={closeImportWizard} />;
}
