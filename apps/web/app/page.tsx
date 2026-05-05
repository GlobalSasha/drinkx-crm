import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-2xl w-full bg-white border border-black/10 rounded-2xl p-12 shadow-soft">
        <div className="font-mono text-xs uppercase tracking-[0.2em] text-muted mb-3">
          Phase 1 · Foundation
        </div>
        <h1 className="text-5xl font-extrabold tracking-tight leading-none mb-6">
          drinkx<span className="text-accent">.</span>crm
        </h1>
        <p className="text-muted mb-8 leading-relaxed">
          Production build. Skeleton only — see <code className="font-mono text-sm">AUTOPILOT.md</code> for the
          roadmap. Prototype with all real screens lives at{" "}
          <a className="text-accent underline" href="https://globalsasha.github.io/drinkx-crm-prototype/">
            globalsasha.github.io/drinkx-crm-prototype
          </a>
          .
        </p>
        <div className="flex gap-3">
          <Link
            href="/today"
            className="inline-flex items-center gap-2 bg-ink text-white rounded-pill px-5 py-3 font-semibold transition-transform duration-700 ease-soft active:scale-[0.98]"
          >
            Today →
          </Link>
          <Link
            href="/pipeline"
            className="inline-flex items-center gap-2 bg-black/5 text-ink rounded-pill px-5 py-3 font-semibold transition-transform duration-700 ease-soft active:scale-[0.98]"
          >
            Pipeline →
          </Link>
        </div>
      </div>
    </main>
  );
}
