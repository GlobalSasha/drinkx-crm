import Link from "next/link";
import { ArrowLeft, Megaphone } from "lucide-react";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { RELEASES } from "@/lib/releases";
import { ReleaseCard } from "@/components/guide/ReleaseCard";

// История версий — полный changelog. На /guide показывается только последняя
// запись; сюда ведёт кнопка «История версий». Данные — общий lib/releases.ts.
export default function ChangelogPage() {
  return (
    <div className={pageContainerVariants({ surface: "reading" })}>
      <Link
        href="/guide"
        className="inline-flex items-center gap-1.5 type-label text-brand-muted-strong hover:text-brand-primary transition-colors mb-4"
      >
        <ArrowLeft size={15} />
        Назад в руководство
      </Link>

      <PageHeader
        icon={<Megaphone size={20} />}
        title="История версий"
        subtitle="Все обновления CRM — что появилось и как этим пользоваться. Новое — сверху."
      />

      <div className="space-y-3 mt-2">
        {RELEASES.map((rel, i) => (
          <ReleaseCard key={i} release={rel} anchorBase="/guide" />
        ))}
      </div>
    </div>
  );
}
