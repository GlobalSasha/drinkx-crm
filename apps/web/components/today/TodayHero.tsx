"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { C } from "@/lib/design-system";

export interface HeroAction {
  href: string;
  label: string;
}

interface Props {
  dateCaption: string;
  greeting: string;
  name: string;
  /** null — данные ещё грузятся. */
  summary: string | null;
  primary?: HeroAction | null;
  secondary?: HeroAction | null;
}

/**
 * Приветствие на /today: героиня DrinkX, «Доброе утро, Имя» и одна-две фразы
 * сводки из реальных цифр. Без анимаций — экран открывают десятки раз в день.
 * На телефоне героиня скрыта: текст важнее, а картинка заняла бы полэкрана.
 */
export function TodayHero({ dateCaption, greeting, name, summary, primary, secondary }: Props) {
  return (
    <section className="relative overflow-hidden bg-white border border-brand-border rounded-card mb-6">
      <div className="grid sm:grid-cols-[200px_minmax(0,1fr)] lg:grid-cols-[240px_minmax(0,1fr)] sm:min-h-60">
        <div className="relative hidden sm:block" aria-hidden>
          <div className="absolute left-1/2 bottom-0 w-48 h-48 -translate-x-1/2 translate-y-1/3 rounded-full bg-brand-soft" />
          <Image
            src="/today/heroine.webp"
            alt=""
            width={448}
            height={560}
            priority
            className="absolute bottom-0 left-1/2 -translate-x-1/2 h-[96%] w-auto max-w-none"
          />
        </div>

        <div className="self-center p-6 sm:py-8 sm:pl-2 sm:pr-8">
          <p className="type-caption text-brand-muted">{dateCaption}</p>
          <h1 className={`type-page-title ${C.color.text} mt-2`}>
            {greeting}, <span className="text-brand-accent-text">{name}</span>!
          </h1>

          {summary == null ? (
            <div className="mt-3 space-y-2" aria-hidden>
              <div className="h-4 w-full max-w-md rounded-full bg-brand-panel animate-pulse" />
              <div className="h-4 w-2/3 max-w-xs rounded-full bg-brand-panel animate-pulse" />
            </div>
          ) : (
            <p className="mt-3 max-w-prose text-lg leading-snug text-brand-muted-strong">{summary}</p>
          )}

          {(primary || secondary) && (
            <div className="mt-6 flex flex-wrap items-center gap-2">
              {primary && (
                <Link
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  href={primary.href as any}
                  className={`h-10 px-5 inline-flex items-center gap-2 rounded-full bg-brand-accent text-white type-caption font-semibold hover:bg-brand-accent/90 active:scale-[0.96] transition-colors ${C.focusRing}`}
                >
                  <span className="truncate max-w-[18rem]">{primary.label}</span>
                  <ArrowRight size={14} aria-hidden />
                </Link>
              )}
              {secondary && (
                <Link
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  href={secondary.href as any}
                  className={`h-10 px-5 inline-flex items-center rounded-full border border-brand-border text-brand-muted type-caption font-semibold hover:bg-brand-panel transition-colors ${C.focusRing}`}
                >
                  {secondary.label}
                </Link>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
