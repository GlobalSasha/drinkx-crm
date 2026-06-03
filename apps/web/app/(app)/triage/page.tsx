import { UnmatchedMessagesSection } from "@/components/inbox/UnmatchedMessagesSection";
import { pageContainerVariants } from "@/components/ui/PageContainer";

export default function TriagePage() {
  return (
    <div className={pageContainerVariants({ width: "content" })}>
      <header className="mb-6">
        <h1 className="text-xl font-bold tracking-tight text-ink">
          Мессенджеры и звонки
        </h1>
        <p className="text-sm text-muted mt-1">
          Сообщения без привязки к лиду — Telegram, MAX, телефон
        </p>
      </header>
      <UnmatchedMessagesSection />
    </div>
  );
}
