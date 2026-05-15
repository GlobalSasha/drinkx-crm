"use client";
import { useMemo, useState } from "react";
import {
  Plus,
  Pencil,
  Phone,
  Mail,
  Linkedin,
  Send as TgSend,
  Instagram,
  Facebook,
  AlertTriangle,
} from "lucide-react";
import { useContacts } from "@/lib/hooks/use-contacts";
import type { ContactOut, LeadOut } from "@/lib/types";
import { C } from "@/lib/design-system";
import { ContactEditModal } from "./ContactEditModal";

interface Props {
  lead: LeadOut;
}

const AVATAR_COLORS = [
  "bg-brand-accent text-white",
  "bg-success text-white",
  "bg-warning text-white",
  "bg-rose text-white",
  "bg-ink text-white",
  "bg-brand-primary text-white",
];

function initialsOf(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

const ROLE_LABELS: Record<string, string> = {
  economic_buyer: "ключевой",
  champion: "чемпион",
  technical_buyer: "технический",
  operational_buyer: "операционный",
};

function colorFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  const idx = Math.abs(hash) % AVATAR_COLORS.length;
  return AVATAR_COLORS[idx];
}

export function ContactsTab({ lead }: Props) {
  const { data: contacts = [], isLoading } = useContacts(lead.id);
  const [editingContact, setEditingContact] = useState<ContactOut | null>(null);
  const [addingNew, setAddingNew] = useState(false);

  const unverifiedCount = useMemo(
    () => contacts.filter((c) => c.verified_status === "to_verify").length,
    [contacts],
  );

  if (isLoading) {
    return (
      <div className={`py-8 text-center type-caption ${C.color.muted}`}>
        Загрузка контактов…
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {unverifiedCount > 0 && (
        <div className="flex items-center gap-2 bg-warning/5 border border-warning/20 rounded-xl px-3.5 py-2.5">
          <AlertTriangle size={14} className="text-warning shrink-0" />
          <p className="type-caption text-warning">
            AI · нужна проверка ({unverifiedCount})
          </p>
        </div>
      )}

      {contacts.length === 0 ? (
        <p className="type-hint text-brand-muted py-6 text-center">
          Контактов пока нет. Добавьте первый — он попадёт в список ЛПР.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {contacts.map((c) => (
            <ContactRow
              key={c.id}
              contact={c}
              onEdit={() => setEditingContact(c)}
            />
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={() => setAddingNew(true)}
        className={`inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold ${C.button.ghost} mt-2`}
      >
        <Plus size={13} />
        Добавить контакт
      </button>

      {(editingContact || addingNew) && (
        <ContactEditModal
          leadId={lead.id}
          contact={editingContact}
          onClose={() => {
            setEditingContact(null);
            setAddingNew(false);
          }}
        />
      )}
    </div>
  );
}

function ContactRow({
  contact,
  onEdit,
}: {
  contact: ContactOut;
  onEdit: () => void;
}) {
  const hasName = !!(contact.name && contact.name.trim());
  const displayName = hasName ? contact.name : "Неизвестный контакт";
  const initials = hasName ? initialsOf(contact.name) : "?";
  const avatarClass = hasName
    ? colorFor(contact.name)
    : "bg-brand-panel text-muted-2";
  const isUnverified = contact.verified_status === "to_verify";
  const roleLabel = contact.role_type ? ROLE_LABELS[contact.role_type] : null;

  return (
    <li
      className="rounded-2xl border border-brand-border bg-white p-3.5 cursor-pointer hover:border-brand-accent transition-colors"
      onClick={onEdit}
      role="button"
    >
      <div className="flex items-start gap-3">
        <span
          className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm ${avatarClass}`}
        >
          {initials}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 flex-wrap">
              <p className={`type-caption font-semibold ${C.color.text}`}>
                {displayName}
              </p>
              {roleLabel && (
                <span className="type-caption font-semibold px-2 py-0.5 rounded-full bg-brand-accent/10 text-brand-accent">
                  {roleLabel}
                </span>
              )}
              {!hasName ? (
                <span className="type-caption font-semibold px-2 py-0.5 rounded-full bg-warning/10 text-warning">
                  уточнить
                </span>
              ) : (
                <VerifyBadge status={contact.verified_status} confidence={contact.confidence} />
              )}
            </div>
            <button
              type="button"
              onClick={onEdit}
              className={`inline-flex items-center gap-1 px-2.5 py-1 type-caption font-semibold ${C.color.muted} hover:${C.color.text} bg-brand-panel rounded-full transition-colors shrink-0`}
            >
              <Pencil size={11} />
              Изменить
            </button>
          </div>

          {contact.title && (
            <p className={`type-caption ${C.color.muted} mt-0.5`}>{contact.title}</p>
          )}

          <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-2.5">
            {contact.phone && (
              <LinkBtn href={`tel:${contact.phone}`} icon={<Phone size={11} />} label={contact.phone} />
            )}
            {contact.email && (
              <LinkBtn href={`mailto:${contact.email}`} icon={<Mail size={11} />} label={contact.email} />
            )}
            {contact.linkedin_url && (
              <LinkBtn
                href={contact.linkedin_url}
                external
                icon={<Linkedin size={11} />}
                label="LinkedIn"
              />
            )}
            {contact.telegram_url && (
              <LinkBtn
                href={contact.telegram_url}
                external
                icon={<TgSend size={11} />}
                label="Telegram"
              />
            )}
            {/* Instagram/Facebook are UI-only fields in the edit modal —
                no backend column yet, so this branch will be silent until
                the schema catches up. Kept here so future links render
                without another touch. */}
            {(contact as ContactOut & { instagram_url?: string | null }).instagram_url && (
              <LinkBtn
                href={(contact as ContactOut & { instagram_url?: string | null }).instagram_url!}
                external
                icon={<Instagram size={11} />}
                label="Instagram"
              />
            )}
            {(contact as ContactOut & { facebook_url?: string | null }).facebook_url && (
              <LinkBtn
                href={(contact as ContactOut & { facebook_url?: string | null }).facebook_url!}
                external
                icon={<Facebook size={11} />}
                label="Facebook"
              />
            )}
          </div>

          {isUnverified && contact.notes && (
            <p className="type-hint text-brand-muted mt-2">
              Источник: {contact.notes.length > 80 ? `${contact.notes.slice(0, 80)}…` : contact.notes}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

function VerifyBadge({
  status,
}: {
  status: string;
  confidence: string;
}) {
  if (status === "verified") return null;
  if (status === "invalid") {
    return (
      <span className="type-caption font-semibold px-2 py-0.5 rounded-full bg-rose/10 text-rose">
        invalid
      </span>
    );
  }
  return (
    <span className="type-caption font-semibold px-2 py-0.5 rounded-full bg-warning/10 text-warning">
      уточнить
    </span>
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
      onClick={(e) => e.stopPropagation()}
      className={`inline-flex items-center gap-1 type-caption ${C.color.muted} hover:${C.color.accent} transition-colors`}
    >
      {icon}
      {label}
    </a>
  );
}
