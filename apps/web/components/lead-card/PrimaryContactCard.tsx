"use client";
import { Phone, Mail, Send as TgSend, Users } from "lucide-react";
import { useContacts } from "@/lib/hooks/use-contacts";
import type { LeadOut } from "@/lib/types";
import { C } from "@/lib/design-system";
import { safeHref } from "@/lib/safe-url";

// Always-visible primary-contact summary for the lead card's left column.
// Shows the lead's primary ЛПР (or the first contact); the full list lives in
// the «Контакты» tab, reachable via onOpenContacts.

const ROLE_LABELS: Record<string, string> = {
  economic_buyer: "ключевой ЛПР",
  champion: "чемпион",
  technical_buyer: "технический",
  operational_buyer: "операционный",
};

const AVATAR_COLORS = [
  "bg-brand-accent",
  "bg-success",
  "bg-warning",
  "bg-rose",
  "bg-brand-primary",
];

function colorFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function initialsOf(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

export function PrimaryContactCard({
  lead,
  onOpenContacts,
}: {
  lead: LeadOut;
  onOpenContacts?: () => void;
}) {
  const { data: contacts = [], isLoading } = useContacts(lead.id);
  if (isLoading) return null;

  const primary =
    contacts.find((c) => c.id === lead.primary_contact_id) ?? contacts[0] ?? null;

  if (!primary) {
    return (
      <div className="rounded-card border border-brand-border bg-white p-4">
        <p className="type-caption text-brand-muted mb-2">Основной контакт</p>
        <p className="type-caption text-brand-muted">Контакт не указан.</p>
        {onOpenContacts && (
          <button
            type="button"
            onClick={onOpenContacts}
            className={`mt-2 inline-flex type-caption font-semibold ${C.color.accent} hover:underline`}
          >
            Добавить контакт →
          </button>
        )}
      </div>
    );
  }

  const hasName = !!(primary.name && primary.name.trim());
  const name = hasName ? primary.name : "Без имени";
  const role = primary.role_type ? ROLE_LABELS[primary.role_type] : null;
  const tg = safeHref(primary.telegram_url);

  return (
    <div className="rounded-card border border-brand-border bg-white p-4">
      <p className="type-caption text-brand-muted mb-2.5">Основной контакт</p>
      <div className="flex items-start gap-3">
        <span
          className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm ${
            hasName ? `${colorFor(primary.name)} text-white` : "bg-brand-panel text-brand-muted"
          }`}
        >
          {hasName ? initialsOf(primary.name) : "?"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className={`type-caption font-semibold ${C.color.text}`}>{name}</p>
            {role && (
              <span className="type-caption font-semibold px-2 py-0.5 rounded-full bg-brand-accent/10 text-brand-accent">
                {role}
              </span>
            )}
          </div>
          {primary.title && (
            <p className={`type-caption ${C.color.muted} mt-0.5`}>{primary.title}</p>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-2">
            {primary.phone && (
              <LinkBtn href={`tel:${primary.phone}`} icon={<Phone size={11} />} label={primary.phone} />
            )}
            {primary.email && (
              <LinkBtn href={`mailto:${primary.email}`} icon={<Mail size={11} />} label={primary.email} />
            )}
            {tg && <LinkBtn href={tg} external icon={<TgSend size={11} />} label="Telegram" />}
          </div>
        </div>
      </div>
      {contacts.length > 1 && onOpenContacts && (
        <button
          type="button"
          onClick={onOpenContacts}
          className={`mt-3 inline-flex items-center gap-1.5 type-caption font-semibold ${C.color.muted} hover:${C.color.accent} transition-colors`}
        >
          <Users size={12} />
          Все контакты ({contacts.length}) →
        </button>
      )}
    </div>
  );
}

function LinkBtn({
  href,
  icon,
  label,
  external,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  external?: boolean;
}) {
  return (
    <a
      href={href}
      target={external ? "_blank" : undefined}
      rel={external ? "noopener noreferrer" : undefined}
      className={`inline-flex items-center gap-1 type-caption ${C.color.muted} hover:${C.color.accent} transition-colors`}
    >
      {icon}
      {label}
    </a>
  );
}
