import { AppShell } from "@/components/layout/AppShell";
import { ImportWizardMount } from "@/components/import/ImportWizardMount";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      {children}
      <ImportWizardMount />
    </AppShell>
  );
}
