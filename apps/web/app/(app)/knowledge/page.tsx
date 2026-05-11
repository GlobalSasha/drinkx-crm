"use client";

// /knowledge — Sprint 3.4 G4 stub. The Knowledge Base UI lands in a
// separate sprint; this page exists so the sidebar link is no longer
// disabled and managers see a clear «Скоро» message instead of a 404.

import { BookOpen } from "lucide-react";

export default function KnowledgePage() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-12">
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft p-10 text-center">
        <div className="w-12 h-12 mx-auto rounded-full bg-brand-soft flex items-center justify-center mb-4">
          <BookOpen size={20} className="text-brand-accent" />
        </div>
        <h1 className="text-lg font-extrabold tracking-tight mb-2">
          База знаний
        </h1>
        <p className="text-sm text-muted-2">Раздел в разработке.</p>
      </div>
    </div>
  );
}
