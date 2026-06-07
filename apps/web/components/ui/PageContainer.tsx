import * as React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * PageContainer — единый фрейм страницы для всех топ-левел экранов.
 *
 * Ширина задаётся АРХЕТИПОМ контента, а не пикселями. Контейнер fluid
 * (заполняет рабочую область, гаттеры растут с вьюпортом) и центрируется
 * только под sanity-cap 1760px на очень широких мониторах — чтобы таблицы
 * не растягивались в нечитаемую строку. Читаемость удерживается на уровне
 * компонента (текст-колонки, блоки форм), а не сужением всей страницы.
 *
 *   data    — таблицы, канбан, дашборды, списки (по умолчанию)
 *   detail  — рабочие поверхности записи (карточка лида и подобные)
 *   reading — проза и формы (читаемый блок внутри кэпится отдельно)
 *
 *   <PageContainer surface="data">…</PageContainer>
 */
export type Surface = "data" | "detail" | "reading";

const pageContainerVariants = cva(
  // fluid-база: заполняем ширину, гаттеры растут, единый вертикальный ритм
  "w-full px-4 sm:px-6 lg:px-8 2xl:px-12 py-6 sm:py-8",
  {
    variants: {
      // Сегодня все три дают одинаковый фрейм; это семантические хуки, чтобы
      // detail (2 колонки) и reading (внутренний ch-cap) могли разойтись
      // позже без правки call-site'ов.
      surface: {
        data: "max-w-[1760px] mx-auto",
        detail: "max-w-[1760px] mx-auto",
        reading: "max-w-[1760px] mx-auto",
      },
    },
    defaultVariants: { surface: "data" },
  },
);

export interface PageContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  surface?: Surface;
}

const PageContainer = React.forwardRef<HTMLDivElement, PageContainerProps>(
  ({ className, surface, ...props }, ref) => (
    <div ref={ref} className={cn(pageContainerVariants({ surface, className }))} {...props} />
  ),
);
PageContainer.displayName = "PageContainer";

export { PageContainer, pageContainerVariants };
