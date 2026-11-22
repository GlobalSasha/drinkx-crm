import type { MetadataRoute } from "next";

/** Installable app («На экран Домой»). iPhone delivers push notifications
 *  only to an installed web app, so this is what makes phase 3 work. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "DrinkX CRM",
    short_name: "DrinkX CRM",
    description: "CRM DrinkX: заявки, лиды и задачи",
    lang: "ru",
    start_url: "/today",
    scope: "/",
    display: "standalone",
    background_color: "#F5F4F0",
    theme_color: "#FFFFFF",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
