import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // taste-soft tokens — see prototype/index-soft-full.html
      colors: {
        canvas: {
          DEFAULT: "#F2F2F0",
          2: "#E8E8E5",
        },
        ink: {
          DEFAULT: "#0A0A0A",
          2: "#18181B",
        },
        muted: {
          DEFAULT: "#57575A",
          2: "#71717A",
          3: "#aeaeb2",
        },
        accent: {
          DEFAULT: "#1F4D3F",
          glow: "#5A8C7A",
          soft: "rgba(31,77,63,0.08)",
        },
        success: "#2D7A5A",
        warning: "#B7672D",
        rose: "#B23A48",
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
      },
      fontFamily: {
        sans: ["var(--font-jakarta)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        lg: "1.5rem",
        xl: "1.75rem",
        "2xl": "2.25rem",
        pill: "999px",
      },
      transitionTimingFunction: {
        "soft": "cubic-bezier(0.32, 0.72, 0, 1)",
        "spring": "cubic-bezier(0.16, 1.16, 0.3, 1)",
      },
      boxShadow: {
        soft: "0 20px 40px -22px rgba(10,10,10,0.08)",
        pill: "0 8px 24px -16px rgba(10,10,10,0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
