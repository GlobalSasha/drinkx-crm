// Design System tokens for DrinkX CRM.
//
// Source of truth: this file. Tailwind config exposes the underlying
// brand-* color tokens; this module composes ready-to-use class strings
// so component code never deals in raw `text-xx`, `bg-xx`, padding values.
//
// Rules baked in:
//   • All buttons -> rounded-full
//   • No hover:* classes (disabled site-wide per design spec)
//   • No shadow-* on cards (only on toasts / popovers handled inline)
//   • All font sizes use clamp() — never text-xs/sm/lg etc.
//
// Usage: `import { C } from '@/lib/design-system'`

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

  // ─── Типографика ─────────────────────────────────────────
  hero:        'text-[clamp(32px,6vw,80px)] font-black',
  h1:          'text-[clamp(26px,4vw,58px)] font-black',
  h2sm:        'text-[clamp(26px,4vw,58px)] font-black',
  h3:          'text-[clamp(17px,1.45vw,21px)] font-black',
  cardTitle:   'text-[clamp(18px,1.7vw,26px)] font-bold',
  cardTitleLg: 'text-[clamp(28px,3.4vw,52px)] font-black',

  body:      'text-[clamp(16px,1.45vw,22px)]',
  bodyHero:  'text-[clamp(18px,1.6vw,26px)]',
  bodySm:    'text-[clamp(14px,1.05vw,16px)]',
  bodyXs:    'text-[clamp(12px,0.9vw,14px)]',
  cardBody:  'text-[clamp(14px,1.05vw,16px)]',
  caption:   'text-[clamp(11px,1.1vw,14px)] uppercase tracking-wider',
  captionSm: 'text-[clamp(12px,1.2vw,16px)]',

  metricHero:      'text-[clamp(40px,7.5vw,100px)] font-black',
  metricLg:        'text-[clamp(32px,5vw,72px)] font-black',
  metricMd:        'text-[clamp(28px,4vw,60px)] font-black',
  metricSm:        'text-[clamp(22px,2.5vw,36px)] font-black',
  metricLabel:     'text-[clamp(14px,1.2vw,22px)]',
  metricLabelSm:   'text-[clamp(11px,0.9vw,14px)]',
  metricLabelHero: 'text-[clamp(18px,1.45vw,24px)]',

  btn:     'text-[clamp(10px,0.9vw,12px)]',
  btnLg:   'text-[clamp(12px,1vw,14px)]',
  btnHero: 'text-[clamp(13px,1.1vw,16px)]',

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
    label: 'text-[clamp(11px,0.9vw,13px)] text-brand-muted uppercase tracking-wide font-medium',
    field: 'w-full bg-white border border-brand-border rounded-full px-4 py-2.5 text-[clamp(13px,1vw,15px)] text-brand-primary outline-none focus:border-brand-accent transition-colors',
  },
} as const;

export type DesignSystem = typeof C;
