// Design System tokens for DrinkX CRM.
//
// Source of truth: this file. Tailwind config exposes the underlying
// brand-* color tokens; this module composes ready-to-use class strings
// so component code never deals in raw `text-xx`, `bg-xx`, padding values.
//
// Typography policy:
//   • Use T.* tokens only — never raw text-[Npx], text-xs/sm/lg, etc.
//   • Weights allowed: font-normal / font-medium / font-semibold / font-bold
//   • Italic only via T.hint (empty-state / unfilled placeholder)
//   • font-mono only for IDs, emails, INN, timestamps, code, webhooks
//
// Usage:
//   import { T, C } from '@/lib/design-system'

// ─── Typography (5 levels + 2 metric + hint) ───────────────────
export const T = {
  display:  'text-3xl md:text-4xl font-bold tracking-tight',
  heading:  'text-lg font-semibold',
  body:     'text-sm font-normal',
  caption:  'text-xs font-medium text-brand-muted uppercase tracking-wide',
  mono:     'font-mono text-xs tracking-normal',
  hint:     'text-xs font-medium italic normal-case tracking-normal text-brand-muted',
  metric:   'text-4xl font-bold tabular-nums',
  metricLg: 'text-5xl font-bold tabular-nums',
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

  // ─── Типографика (back-compat aliases → T.*) ─────────────
  // New code: use T.* directly. These aliases keep existing call sites
  // working while the sweep migrates them over.
  hero:        T.display,
  h1:          T.heading,
  h2sm:        T.heading,
  h3:          T.heading,
  cardTitle:   T.heading,
  cardTitleLg: T.display,

  body:      T.body,
  bodyHero:  T.body,
  bodySm:    T.caption,
  bodyXs:    T.caption,
  cardBody:  T.caption,
  caption:   T.caption,
  captionSm: T.caption,

  metricHero:      T.metricLg,
  metricLg:        T.metricLg,
  metricMd:        T.metric,
  metricSm:        T.metric,
  metricLabel:     T.caption,
  metricLabelSm:   T.caption,
  metricLabelHero: T.caption,

  btn:     T.body,
  btnLg:   T.body,
  btnHero: T.body,

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
  button: {
    primary: 'bg-brand-accent text-white rounded-full font-medium transition-opacity',
    pill:    'bg-brand-panel text-brand-muted-strong border border-brand-border rounded-full font-medium',
    nav:     'bg-brand-panel text-brand-primary rounded-full font-medium',
    ghost:   'bg-transparent text-brand-muted border border-brand-border rounded-full font-medium',
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
    field: 'w-full bg-white border border-brand-border rounded-full px-4 py-2.5 text-sm text-brand-primary outline-none focus:border-brand-accent transition-colors',
  },
} as const;

export type DesignSystem = typeof C;
