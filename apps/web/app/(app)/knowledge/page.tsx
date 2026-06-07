"use client";

// /knowledge — placeholder until the full KB UI lands. Originally a Sprint 3.4 G4
// stub; expanded in Sprint 3.5 to give managers a clearer roadmap-style message
// instead of a flat "Раздел в разработке." dead end.

import { BookOpen, Sparkles } from "lucide-react";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";

export default function KnowledgePage() {
  return (
    <div className={pageContainerVariants({ width: "wide" })}>
      <PageHeader
        icon={<BookOpen size={20} />}
        title="База знаний"
        subtitle="Раздел в разработке"
      />
      <div className="bg-white border border-brand-border rounded-[2rem] p-10">
        <p className="text-sm text-brand-muted leading-relaxed mb-5">
          Здесь будут жить сегментные плейбуки, скрипты возражений и шаблоны коммерческих
          предложений. Блейк будет ссылаться на материалы прямо из ленты лида, а менеджеры
          смогут открывать плейбук по нажатию на сегмент сделки.
        </p>

        <ul className="text-sm text-brand-muted space-y-2 mb-6">
          <li className="flex items-start gap-2">
            <Sparkles size={14} className="text-brand-accent shrink-0 mt-0.5" />
            <span>Плейбуки по сегментам — HoReCa, QSR, ритейл, АЗС.</span>
          </li>
          <li className="flex items-start gap-2">
            <Sparkles size={14} className="text-brand-accent shrink-0 mt-0.5" />
            <span>Шаблоны писем и сценарии переговоров под каждый этап воронки.</span>
          </li>
          <li className="flex items-start gap-2">
            <Sparkles size={14} className="text-brand-accent shrink-0 mt-0.5" />
            <span>Конкурентная разведка — battle cards по основным игрокам рынка.</span>
          </li>
        </ul>

        <div className="text-xs text-brand-muted border-t border-brand-border pt-4">
          Пока материалы готовятся, Блейк уже умеет отвечать на вопросы по продукту и
          возражениям прямо в ленте лида — задайте @Блейк вопрос в любой карточке.
        </div>
      </div>
    </div>
  );
}
