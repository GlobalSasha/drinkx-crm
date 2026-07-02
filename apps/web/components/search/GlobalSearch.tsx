"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, Building2, Briefcase, User, FileText, X, Loader2 } from "lucide-react";
import { useGlobalSearch } from "@/lib/hooks/use-search";
import type { SearchHit, SearchHitType } from "@/lib/types";
import { C, T } from "@/lib/design-system";

const TYPE_LABEL: Record<SearchHitType, string> = {
  company: "Компании",
  lead: "Лиды",
  contact: "Контакты",
  file: "Файлы",
};

const TYPE_ICON: Record<SearchHitType, React.ReactNode> = {
  company: <Building2 size={14} />,
  lead: <Briefcase size={14} />,
  contact: <User size={14} />,
  file: <FileText size={14} />,
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export function GlobalSearch({ open, onClose }: Props) {
  const [query, setQuery] = useState("");
  const router = useRouter();
  const { data, isFetching } = useGlobalSearch(query, 20);
  const [activeIdx, setActiveIdx] = useState(0);

  useEffect(() => {
    if (open) setQuery("");
  }, [open]);

  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  const grouped = useMemo(() => {
    const items = data?.items ?? [];
    const groups: Record<SearchHitType, SearchHit[]> = {
      company: [],
      lead: [],
      contact: [],
      file: [],
    };
    for (const it of items) groups[it.type].push(it);
    return groups;
  }, [data]);

  const flat = useMemo<SearchHit[]>(() => {
    const order: SearchHitType[] = ["company", "lead", "contact", "file"];
    return order.flatMap((t) => grouped[t]);
  }, [grouped]);

  function navigate(hit: SearchHit) {
    onClose();
    router.push(hit.url as Parameters<typeof router.push>[0]);
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      onClose();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && flat[activeIdx]) {
      e.preventDefault();
      navigate(flat[activeIdx]);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-4 pt-20"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-3xl max-w-xl w-full shadow-overlay overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-5 py-4 border-b border-brand-border">
          <Search size={18} className={C.color.muted} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Поиск компаний, лидов, контактов…"
            autoFocus
            className={`flex-1 type-card-title font-medium ${C.color.text} bg-transparent outline-none placeholder:${C.color.muted}`}
          />
          {isFetching && <Loader2 size={14} className="animate-spin text-brand-muted" />}
          <button
            type="button"
            onClick={onClose}
            className="p-2.5 -m-1.5 rounded-full hover:bg-brand-panel transition-colors"
            aria-label="Закрыть"
          >
            <X size={18} className={C.color.muted} />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {!query.trim() && (
            <div className="flex flex-col items-center gap-3 px-5 py-10 text-center">
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-panel text-brand-muted">
                <Search size={18} />
              </span>
              <p className={`type-body font-medium ${C.color.text}`}>
                Начните печатать, чтобы искать
              </p>
              <p className="type-caption text-brand-muted">
                Компании · Лиды · Контакты · Файлы
              </p>
              <div className="mt-1 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 type-caption text-brand-muted">
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>↑</Kbd>
                  <Kbd>↓</Kbd>
                  навигация
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>↵</Kbd>
                  открыть
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>Esc</Kbd>
                  закрыть
                </span>
              </div>
            </div>
          )}

          {query.trim() && flat.length === 0 && !isFetching && (
            <div className="flex flex-col items-center gap-2 px-5 py-10 text-center">
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-panel text-brand-muted">
                <Search size={18} />
              </span>
              <p className={`type-body font-medium ${C.color.text}`}>
                Ничего не найдено
              </p>
              <p className="type-caption text-brand-muted">
                Попробуйте другой запрос
              </p>
            </div>
          )}

          {(["company", "lead", "contact", "file"] as SearchHitType[]).map((type) => {
            const items = grouped[type];
            if (items.length === 0) return null;
            return (
              <section key={type} className="py-2">
                <h3
                  className="px-5 py-1 type-caption text-brand-muted"
                >
                  {TYPE_LABEL[type]} · {items.length}
                </h3>
                <ul>
                  {items.map((it) => {
                    const globalIdx = flat.indexOf(it);
                    const isActive = globalIdx === activeIdx;
                    return (
                      <li key={`${it.type}-${it.id}`}>
                        <button
                          type="button"
                          onClick={() => navigate(it)}
                          onMouseEnter={() => setActiveIdx(globalIdx)}
                          className={`flex items-center gap-3 w-full px-5 py-2.5 text-left transition-colors ${
                            isActive ? "bg-brand-bg" : ""
                          }`}
                        >
                          <span className={C.color.muted}>{TYPE_ICON[it.type]}</span>
                          <span className="flex-1 min-w-0">
                            <span
                              className={`type-caption font-semibold ${C.color.text} truncate block`}
                            >
                              {it.title || "—"}
                            </span>
                            {it.subtitle && (
                              <span
                                className={`type-caption ${C.color.muted} truncate block`}
                              >
                                {it.subtitle}
                              </span>
                            )}
                          </span>
                          {it.rank != null && (
                            <span className={`${T.mono} ${C.color.muted}`}>
                              {it.rank.toFixed(2)}
                            </span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** Keycap chip — renders a single key as a small bordered cap so the
 *  shortcut hints read as keys, not run-in text (make-interfaces-feel-better:
 *  subtle shadow for depth, min-width keeps single glyphs square). */
function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex min-w-[1.5rem] items-center justify-center rounded-md border border-brand-border bg-white px-1.5 py-0.5 font-mono text-2xs font-medium leading-none text-brand-muted-strong shadow-[0_1px_0_rgba(17,17,17,0.06)]">
      {children}
    </kbd>
  );
}

/** Hotkey hook — Cmd+K (mac) / Ctrl+K (others). Mount once in the
 *  app shell; calls `onOpen` when triggered. */
export function useGlobalSearchHotkey(onOpen: () => void) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const isMac = navigator.platform.toLowerCase().includes("mac");
      const cmdOrCtrl = isMac ? e.metaKey : e.ctrlKey;
      if (cmdOrCtrl && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpen();
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onOpen]);
}
