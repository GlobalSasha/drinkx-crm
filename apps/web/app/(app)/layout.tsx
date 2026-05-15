import { AppShell } from "@/components/layout/AppShell";
import { ImportWizardMount } from "@/components/import/ImportWizardMount";
import { ThemeApplier } from "@/components/layout/ThemeApplier";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <ThemeApplier />
      {children}
      <ImportWizardMount />
    </AppShell>
  );
}
