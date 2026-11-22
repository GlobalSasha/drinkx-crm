import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "./providers";

// Шрифты лежат в репозитории (app/fonts, лицензия OFL рядом), а не качаются
// из Google Fonts на сборке: сборка не зависит от сети, а сбой загрузки
// шрифта однажды уронил проверки PR. Оба файла — вариативные, покрывают
// латиницу и кириллицу; веса берутся из оси wght.
const manrope = localFont({
  src: "./fonts/Manrope-Variable.woff2",
  weight: "200 800",
  variable: "--font-ui",
  display: "swap",
});

const mono = localFont({
  src: "./fonts/JetBrainsMono-Variable.woff2",
  weight: "100 800",
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DrinkX CRM",
  description: "Smart AI CRM for B2B coffee station sales",
  // «На экран Домой»: on iPhone push notifications only work for the
  // installed app, so it must open full-screen with our own icon.
  appleWebApp: { capable: true, title: "DrinkX CRM", statusBarStyle: "default" },
  icons: {
    icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#FFFFFF",
  // viewportFit: cover — lets env(safe-area-inset-*) work on notched phones
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className={`${manrope.variable} ${mono.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
