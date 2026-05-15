// Design System tokens for DrinkX CRM.
//
// Source of truth: this file. Tailwind config exposes the underlying
// brand-* color tokens; this module composes ready-to-use class strings
// so component code never deals in raw `bg-xx`, padding, etc.
//
// Typography policy:
//   • Typography lives in globals.css as `.type-*` utility classes
//     (type-page-title, type-card-title, type-body, type-caption,
//     type-hint, type-kpi-number, type-kpi-number-lg, etc.).
//     This file only retains `T.mono` for IDs, emails, INN,
//     timestamps, code, webhooks.
//
// Usage:
//   import { T, C } from '@/lib/design-system'

// ─── Mono (only surviving T token) ─────────────────────────────
export const T = {
  mono: 'font-mono text-xs tracking-normal',
} as const;

export type Typography = typeof T;

export const C = {
  // ─── Цвета ───────────────────────────────────────────────
  color: {
    text:       'text-brand-primary',
    muted:      'text-brand-muted-strong',
    mutedLight: 'text-brand-muted',
    accent:     'text-brand-accent',
    accentBg:   'bg-brand-accent',
  },
  surface: {
    page:  'bg-brand-bg',
    white: 'bg-white',
    dark:  'bg-brand-dark text-white',
    panel: 'bg-brand-panel',
  },
  border: {
    subtle: 'border-brand-border',
    dark:   'border-white/10',
  },

  // ─── Радиусы ─────────────────────────────────────────────
  radius: {
    sm:   'rounded-full',
    md:   'rounded-2xl',
    lg:   'rounded-[2rem]',
    pill: 'rounded-full',
  },

  // ─── Карточки (без тени) ─────────────────────────────────
  card: {
    base:         'bg-white border border-brand-border rounded-[2rem] p-6',
    dark:         'bg-brand-dark text-white rounded-[2rem] p-6',
    panel:        'bg-brand-panel border border-brand-border rounded-[2rem] p-6',
    accent:       'bg-brand-soft border border-brand-accent/20 rounded-[2rem] p-6',
    mediaOverlay: 'absolute inset-0 bg-gradient-to-t from-black/60 to-transparent rounded-[2rem]',
  },

  // ─── Кнопки (всегда rounded-full) ────────────────────────
  // focusRing — общий visible-only ring для клавиатурной навигации
  // (применяется к кнопкам, ссылкам, интерактивным карточкам).
  focusRing: 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg',
  button: {
    primary: 'bg-brand-accent text-white rounded-full font-medium transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg',
    pill:    'bg-brand-panel text-brand-muted-strong border border-brand-border rounded-full font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg',
    nav:     'bg-brand-panel text-brand-primary rounded-full font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg',
    ghost:   'bg-transparent text-brand-muted border border-brand-border rounded-full font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg',
  },

  // ─── Layout ──────────────────────────────────────────────
  layout: {
    maxW:           'max-w-[1800px]',
    px:             'px-4 md:px-6',
    ptNav:          'pt-[112px]',
    pbSection:      'pb-[6vh]',
    subtitle:       'max-w-4xl',
    subtitleNarrow: 'max-w-2xl',
    gap:            'gap-4',
    gapLg:          'gap-6 lg:gap-8',
    headerMb:       'mb-6',
  },

  // ─── Формы ───────────────────────────────────────────────
  form: {
    label: 'text-xs font-medium text-brand-muted uppercase tracking-wide',
    field: 'w-full bg-white border border-brand-border rounded-full px-4 py-2.5 text-sm text-brand-primary outline-none focus:border-brand-accent focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 focus-visible:ring-offset-brand-bg transition-colors',
  },
} as const;

export type DesignSystem = typeof C;
