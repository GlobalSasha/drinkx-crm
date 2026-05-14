"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Check } from "lucide-react";

interface Props {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  counts?: Record<string, number>;
  align?: "left" | "right";
  emptyText?: string;
}

export function MultiSelectDropdown({
  label,
  options,
  selected,
  onChange,
  counts,
  align = "left",
  emptyText,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onMouseDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const isActive = selected.length > 0;
  const buttonText =
    selected.length === 0
      ? label
      : selected.length === 1
        ? `${label}: ${selected[0]}`
        : `${label}: ${selected.length} выбрано`;

  function toggle(opt: string) {
    if (selected.includes(opt)) {
      onChange(selected.filter((s) => s !== opt));
    } else {
      onChange([...selected, opt]);
    }
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`h-8 inline-flex items-center gap-1.5 px-3 rounded-pill text-xs font-semibold transition-all duration-300 ${
          isActive
            ? "bg-brand-accent text-white"
            : "bg-canvas text-muted hover:bg-canvas-2 border border-black/5"
        }`}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="max-w-[14rem] truncate">{buttonText}</span>
        <ChevronDown
          size={13}
          className={`shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          className={`absolute top-full mt-1.5 z-30 min-w-[14rem] max-w-[20rem] max-h-[20rem] flex flex-col bg-white border border-black/10 rounded-xl shadow-[0_8px_32px_-4px_rgba(0,0,0,0.12)] overflow-hidden ${
            align === "right" ? "right-0" : "left-0"
          }`}
          role="listbox"
        >
          <ul className="flex-1 overflow-y-auto py-1">
            {options.length === 0 && (
              <li className="px-3 py-2 text-xs text-muted-3">
                {emptyText ?? "Нет вариантов"}
              </li>
            )}
            {options.map((opt) => {
              const checked = selected.includes(opt);
              const count = counts?.[opt];
              return (
                <li key={opt}>
                  <button
                    type="button"
                    onClick={() => toggle(opt)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-canvas transition-colors duration-150"
                    role="option"
                    aria-selected={checked}
                  >
                    <span
                      className={`w-4 h-4 shrink-0 rounded border flex items-center justify-center transition-all duration-150 ${
                        checked
                          ? "bg-brand-accent border-brand-accent"
                          : "bg-white border-black/20"
                      }`}
                    >
                      {checked && <Check size={11} className="text-white" />}
                    </span>
                    <span className="flex-1 truncate text-ink">{opt}</span>
                    {count !== undefined && (
                      <span className="text-[11px] font-mono text-muted-3 tabular-nums">
                        {count}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
          {selected.length > 0 && (
            <div className="border-t border-black/5 px-3 py-2 bg-canvas/60">
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-xs font-semibold text-muted hover:text-ink transition-colors"
              >
                Сбросить
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
