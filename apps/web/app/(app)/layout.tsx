import { AppShell } from "@/components/layout/AppShell";
import { ImportWizardMount } from "@/components/import/ImportWizardMount";
import { ThemeApplier } from "@/components/layout/ThemeApplier";
import { PresenceHeartbeat } from "@/components/layout/PresenceHeartbeat";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <ThemeApplier />
      <PresenceHeartbeat />
      {children}
      <ImportWizardMount />
    </AppShell>
  );
}
