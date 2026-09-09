"use client";

import { C } from "@/lib/design-system";

interface Props {
  count: number;
  onAssign: () => void;
  onClear: () => void;
}

/**
 * Полоса выделения под таблицей пула. `sticky`, не `fixed` — снизу справа
 * уже живут тосты (`fixed bottom-6 right-6 z-50`) и глобальные напоминания
 * (`fixed bottom z-40`), панель не должна с ними спорить за нижний край.
 */
export function SelectionBar({ count, onAssign, onClear }: Props) {
  return (
    <div
      role="region"
      aria-label="Выделенные карточки"
      className="sticky bottom-0 bg-white border-t border-brand-border px-4 py-3 flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4"
    >
      <span className="text-sm font-semibold text-brand-primary tabular-nums">
        Выбрано: {count}
      </span>
      <div className="flex items-center gap-3 sm:ml-auto">
        <button
          type="button"
          onClick={onAssign}
          disabled={count === 0}
          className={`${C.button.primary} type-body px-4 py-2 flex-1 sm:flex-none disabled:opacity-40`}
        >
          Выдать менеджеру
        </button>
        <button
          type="button"
          onClick={onClear}
          className="text-sm text-brand-muted hover:text-brand-primary flex-1 sm:flex-none"
        >
          Снять выделение
        </button>
      </div>
    </div>
  );
}
