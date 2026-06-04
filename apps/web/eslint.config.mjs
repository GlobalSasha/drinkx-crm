import { FlatCompat } from "@eslint/eslintrc";
import path from "node:path";
import { fileURLToPath } from "node:url";

// FlatCompat bridges Next.js's legacy `.eslintrc`-style configs into
// ESLint 9's flat-config — eslint-config-next ≤15.5 still ships the
// classic `extends: [...]` shape, so we can't spread it directly.
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const compat = new FlatCompat({ baseDirectory: __dirname });

// Arbitrary px Tailwind values (`text-[28px]`, `border-[1.5px]`) drift away
// from the 4-8-12-16-24-32 spacing/type scale. This local rule flags new ones
// at WARN level — it does not fail the build, and the ~229 pre-existing usages
// are deliberately left untouched (a separate mechanical sweep, see BACKLOG).
const ARBITRARY_PX = /-\[\d*\.?\d+px\]/;

const drinkxPlugin = {
  rules: {
    "no-arbitrary-px": {
      meta: {
        type: "suggestion",
        docs: { description: "Disallow arbitrary px Tailwind sizes; use the spacing/type scale." },
        schema: [],
        messages: {
          arbitrary:
            "Arbitrary px size `{{match}}` — prefer the 4-8-12-16-24-32 scale (or a design token).",
        },
      },
      create(context) {
        function check(node, raw) {
          const m = typeof raw === "string" && raw.match(ARBITRARY_PX);
          if (m) context.report({ node, messageId: "arbitrary", data: { match: m[0] } });
        }
        return {
          Literal(node) {
            if (typeof node.value === "string") check(node, node.value);
          },
          TemplateElement(node) {
            check(node, node.value?.raw);
          },
        };
      },
    },
  },
};

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
    ],
  },
  {
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}"],
    plugins: { drinkx: drinkxPlugin },
    rules: { "drinkx/no-arbitrary-px": "warn" },
  },
];

export default eslintConfig;
