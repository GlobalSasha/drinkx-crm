"use client";
import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Users } from "lucide-react";

export interface OwnerOption {
  id: string;
  name: string;
  avatarUrl?: string | null;
}

interface Props {
  /** "" = мои лиды, "all" = все, иначе id менеджера. */
  value: string;
  onChange: (next: string) => void;
  me: OwnerOption | null;
  users: OwnerOption[];
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

function Avatar({ name, url }: { name: string; url?: string | null }) {
  return (
    <span className="w-6 h-6 shrink-0 rounded-full bg-brand-soft text-brand-accent text-xs font-semibold flex items-center justify-center overflow-hidden">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="w-full h-full object-cover" referrerPolicy="no-referrer" />
      ) : (
        initials(name) || "?"
      )}
    </span>
  );
}

/** Выбор «Ответственный» на /pipeline — в том же виде, что фильтры
 *  Сегмент/Страна/Город, но один вариант и с аватарками. */
export function OwnerScopeDropdown({ value, onChange, me, users }: Props) {
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

  const selectedUser = users.find((u) => u.id === value);
  const currentLabel =
    value === "" ? "Мои" : value === "all" ? "Все" : selectedUser?.name ?? "—";
  const isActive = value !== "";

  function pick(next: string) {
    onChange(next);
    setOpen(false);
  }

  const rows: { key: string; label: string; icon: React.ReactNode }[] = [
    {
      key: "",
      label: "Мои",
      icon: <Avatar name={me?.name ?? "Я"} url={me?.avatarUrl} />,
    },
    {
      key: "all",
      label: "Все",
      icon: (
        <span className="w-6 h-6 shrink-0 rounded-full bg-brand-bg border border-brand-border text-brand-muted flex items-center justify-center">
          <Users size={13} />
        </span>
      ),
    },
    ...users.map((u) => ({
      key: u.id,
      label: u.name,
      icon: <Avatar name={u.name} url={u.avatarUrl} />,
    })),
  ];

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`h-8 inline-flex items-center gap-1.5 px-3 rounded-full text-xs font-semibold transition duration-300 ${
          isActive
            ? "bg-brand-accent text-white"
            : "bg-brand-bg text-brand-muted hover:bg-brand-panel border border-brand-border"
        }`}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="max-w-[14rem] truncate">Ответственный: {currentLabel}</span>
        <ChevronDown
          size={13}
          className={`shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1.5 z-30 min-w-[14rem] max-w-[min(20rem,calc(100vw-2rem))] max-h-[20rem] flex flex-col bg-white border border-brand-border rounded-xl shadow-[0_8px_32px_-4px_rgba(0,0,0,0.12)] overflow-hidden">
          <ul role="listbox" aria-label="Ответственный" className="flex-1 overflow-y-auto py-1">
            {rows.map((row, i) => {
              const checked = row.key === value;
              return (
                <li key={row.key || "me"}>
                  {i === 2 && <div className="my-1 border-t border-brand-border" />}
                  <button
                    type="button"
                    role="option"
                    aria-selected={checked}
                    onClick={() => pick(row.key)}
                    className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors duration-150 ${
                      checked ? "bg-brand-soft" : "hover:bg-brand-bg"
                    }`}
                  >
                    {row.icon}
                    <span className="flex-1 truncate text-brand-primary">{row.label}</span>
                    {checked && <Check size={14} className="shrink-0 text-brand-accent" />}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
