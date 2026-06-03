import { UnmatchedMessagesSection } from "@/components/inbox/UnmatchedMessagesSection";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";

export default function TriagePage() {
  return (
    <div className={pageContainerVariants({ width: "content" })}>
      <PageHeader
        title="Мессенджеры и звонки"
        subtitle="Сообщения без привязки к лиду — Telegram, MAX, телефон"
      />
      <UnmatchedMessagesSection />
    </div>
  );
}
