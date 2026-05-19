import { UnmatchedMessagesSection } from "@/components/inbox/UnmatchedMessagesSection";

export default function TriagePage() {
  return (
    <div className="px-6 py-6 md:px-10 md:py-8 max-w-[920px] mx-auto">
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
