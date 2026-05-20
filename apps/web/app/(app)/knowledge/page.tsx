"use client";

// /knowledge — placeholder until the full KB UI lands. Originally a Sprint 3.4 G4
// stub; expanded in Sprint 3.5 to give managers a clearer roadmap-style message
// instead of a flat "Раздел в разработке." dead end.

import { BookOpen, Sparkles } from "lucide-react";

export default function KnowledgePage() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-12">
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-10">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-full bg-brand-soft flex items-center justify-center">
            <BookOpen size={20} className="text-brand-accent" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight">База знаний</h1>
            <p className="text-xs text-muted-2">Раздел в разработке</p>
          </div>
        </div>

        <p className="text-sm text-muted-2 leading-relaxed mb-5">
          Здесь будут жить сегментные плейбуки, скрипты возражений и шаблоны коммерческих
          предложений. Блейк будет ссылаться на материалы прямо из ленты лида, а менеджеры
          смогут открывать плейбук по нажатию на сегмент сделки.
        </p>

        <ul className="text-sm text-muted-2 space-y-2 mb-6">
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

        <div className="text-xs text-muted-2 border-t border-black/5 pt-4">
          Пока материалы готовятся, Блейк уже умеет отвечать на вопросы по продукту и
          возражениям прямо в ленте лида — задайте @Блейк вопрос в любой карточке.
        </div>
      </div>
    </div>
  );
}
