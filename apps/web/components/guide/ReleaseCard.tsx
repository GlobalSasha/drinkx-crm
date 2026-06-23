import { CheckCircle2, Sparkles } from "lucide-react";
import type { Release } from "@/lib/releases";

// One «Что нового» release rendered as a card. Shared by the /guide section
// (latest only, `featured`) and the /guide/changelog history page (full list).
//
// `anchorBase` prefixes the feature links: "" keeps same-page jumps on /guide
// (`#quote`); "/guide" makes them work from the changelog page (`/guide#quote`).
export function ReleaseCard({
  release,
  anchorBase = "",
  featured = false,
}: {
  release: Release;
  anchorBase?: string;
  featured?: boolean;
}) {
  return (
    <div
      className={`bg-white rounded-card p-6 border ${
        featured ? "border-brand-accent/40 ring-1 ring-brand-accent/15" : "border-brand-border"
      }`}
    >
      {featured && (
        <div className="type-caption font-semibold text-brand-accent mb-2">
          Последнее обновление
        </div>
      )}
      <div className="flex items-center flex-wrap gap-2 mb-3">
        <span className="inline-flex items-center gap-1.5 bg-brand-accent text-white type-caption font-semibold px-2.5 py-0.5 rounded-full">
          <Sparkles size={12} /> {release.version}
        </span>
        <h3 className="type-card-title text-brand-primary">{release.title}</h3>
        <span className="type-hint text-brand-muted ml-auto">{release.date}</span>
      </div>
      <ul className="space-y-2.5">
        {release.items.map((it, j) => (
          <li key={j} className="flex gap-2.5">
            <CheckCircle2 size={15} className="text-brand-accent shrink-0 mt-0.5" />
            <div>
              <span className="type-label text-brand-primary">
                {it.anchor ? (
                  <a
                    href={`${anchorBase}#${it.anchor}`}
                    className="underline decoration-brand-border underline-offset-2 hover:text-brand-accent transition-colors"
                  >
                    {it.feature}
                  </a>
                ) : (
                  it.feature
                )}
              </span>
              <span className="type-body text-brand-muted-strong"> — {it.how}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
