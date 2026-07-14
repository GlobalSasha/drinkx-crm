import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // taste-soft tokens — see prototype/index-soft-full.html
      colors: {
        success: "#2D7A5A",
        warning: "#B7672D",
        rose: "#B23A48",
        info: "#2B5BA8",
        // ─── Design System (DrinkX brand) ─────────────────────
        // Consumed via the C object in lib/design-system.ts.
        // Direct usage as Tailwind classes is allowed but should
        // go through C tokens for consistency.
        brand: {
          accent:         "#FF4E00",
          "accent-text":  "#D63F00",
          soft:           "#FFE1D6",
          primary:        "#111111",
          "muted-strong": "#1A1A1A",
          muted:          "#6B6B6B",
          bg:             "#F5F4F0",
          panel:          "#E5E3DC",
          border:         "#D6D4CE",
          dark:           "#111111",
        },
        // Категориальная палитра графиков — только существующие токены,
        // порядок закреплён в .interface-design/system.md.
        chart: {
          1: "#FF4E00",
          2: "#2B5BA8",
          3: "#2D7A5A",
          4: "#B7672D",
          5: "#B23A48",
          6: "#6B6B6B",
        },
      },
      fontFamily: {
        sans: ["var(--font-ui)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
        ui: ["var(--font-ui)", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        display: ["var(--font-ui)", "sans-serif"],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "1.3" }],
        xs:    ["11px", { lineHeight: "1.4" }],
        sm:    ["12px", { lineHeight: "1.4" }],
        md:    ["13px", { lineHeight: "1.4" }],
        base:  ["14px", { lineHeight: "1.5" }],
        lg:    ["16px", { lineHeight: "1.3" }],
        xl:    ["18px", { lineHeight: "1.3" }],
        "2xl": ["20px", { lineHeight: "1.3" }],
        "3xl": ["24px", { lineHeight: "1.2" }],
        "4xl": ["28px", { lineHeight: "1.2" }],
        "5xl": ["32px", { lineHeight: "1.1" }],
      },
      letterSpacing: {
        tight:  "-0.02em",
        snug:   "-0.01em",
        normal: "0",
        wide:   "0.02em",
        wider:  "0.04em",
        widest: "0.06em",
      },
      borderRadius: {
        // md переопределён (Tailwind-дефолт 6px чужероден мягкой системе):
        // мелкие вложенные элементы — пункты меню, миниатюры, строки-ховеры.
        md: "0.75rem",
        lg: "1.5rem",
        xl: "1.75rem",
        card: "2rem",
      },
      transitionTimingFunction: {
        // `spring` (перелёт >1) удалён 2026-07-14: нигде не использовался,
        // а пружинность не в характере системы. Единственная кривая — soft.
        "soft": "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      boxShadow: {
        // Single elevation for true overlays (modals, dropdowns, popovers,
        // drawers, tooltips, toasts). Cards stay shadowless.
        overlay: "0 16px 48px -16px rgba(17,17,17,0.18)",
      },
    },
  },
  plugins: [
    // coarse: — touch-primary devices (phones/tablets). Used to keep
    // hover-revealed controls always visible where hover doesn't exist.
    plugin(({ addVariant }) => addVariant("coarse", "@media (pointer: coarse)")),
  ],
};

export default config;
