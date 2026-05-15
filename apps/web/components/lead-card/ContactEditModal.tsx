"use client";
import { useState } from "react";
import {
  Phone,
  Mail,
  Linkedin,
  Send as TgSend,
  Instagram,
  Facebook,
  Trash2,
} from "lucide-react";
import {
  useCreateContact,
  useUpdateContact,
  useDeleteContact,
} from "@/lib/hooks/use-contacts";
import type { ContactOut, ContactCreate, ContactRoleType } from "@/lib/types";
import { C } from "@/lib/design-system";
import { Modal } from "@/components/ui/Modal";

/** Internal form shape — adds front-end-only fields that aren't on the
 *  backend Contact model yet (last_name, middle_name, company, dept,
 *  instagram, facebook). They live in the modal state and are NOT sent
 *  to the API. The "name" field on the backend is whatever the manager
 *  composes from "Фамилия + Имя + Отчество". */
interface FormState {
  last_name: string;
  first_name: string;
  middle_name: string;
  title: string;
  company: string;
  department: string;
  phone: string;
  email: string;
  linkedin_url: string;
  telegram_url: string;
  instagram_url: string;
  facebook_url: string;
  role_type: ContactRoleType | "";
  confidence: "high" | "medium" | "low";
  verified_status: "verified" | "to_verify" | "invalid";
  notes: string;
}

function splitName(full: string): { last: string; first: string; middle: string } {
  const parts = (full || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return { last: "", first: "", middle: "" };
  if (parts.length === 1) return { last: "", first: parts[0], middle: "" };
  if (parts.length === 2) return { last: parts[0], first: parts[1], middle: "" };
  return { last: parts[0], first: parts[1], middle: parts.slice(2).join(" ") };
}

function joinName(last: string, first: string, middle: string): string {
  return [last, first, middle].map((s) => s.trim()).filter(Boolean).join(" ");
}

const EMPTY_FORM: FormState = {
  last_name: "",
  first_name: "",
  middle_name: "",
  title: "",
  company: "",
  department: "",
  phone: "",
  email: "",
  linkedin_url: "",
  telegram_url: "",
  instagram_url: "",
  facebook_url: "",
  role_type: "",
  confidence: "medium",
  verified_status: "to_verify",
  notes: "",
};

interface Props {
  leadId: string;
  contact: ContactOut | null;
  onClose: () => void;
}

export function ContactEditModal({ leadId, contact, onClose }: Props) {
  const create = useCreateContact(leadId);
  const update = useUpdateContact(leadId, contact?.id ?? "");
  const del = useDeleteContact(leadId);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const [form, setForm] = useState<FormState>(() => {
    if (!contact) return EMPTY_FORM;
    const split = splitName(contact.name);
    return {
      ...EMPTY_FORM,
      last_name: split.last,
      first_name: split.first,
      middle_name: split.middle,
      title: contact.title ?? "",
      phone: contact.phone ?? "",
      email: contact.email ?? "",
      linkedin_url: contact.linkedin_url ?? "",
      telegram_url: contact.telegram_url ?? "",
      role_type: contact.role_type ?? "",
      confidence: (contact.confidence as FormState["confidence"]) ?? "medium",
      verified_status: contact.verified_status as FormState["verified_status"],
      notes: contact.notes ?? "",
    };
  });

  function patch<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  function handleSave(e: React.FormEvent) {
    e.preventDefault();
    const fullName = joinName(form.last_name, form.first_name, form.middle_name);
    if (!fullName) return;
    const body: ContactCreate = {
      name: fullName,
      title: form.title || null,
      role_type: (form.role_type || null) as ContactRoleType | null,
      email: form.email || null,
      phone: form.phone || null,
      telegram_url: form.telegram_url || null,
      linkedin_url: form.linkedin_url || null,
      source: contact?.source ?? "manual",
      confidence: form.confidence,
      verified_status: form.verified_status,
      notes: form.notes || null,
    };
    if (contact) {
      update.mutate(body, { onSuccess: () => onClose() });
    } else {
      create.mutate(body, { onSuccess: () => onClose() });
    }
  }

  function handleDelete() {
    if (!contact) return;
    del.mutate(contact.id, { onSuccess: () => onClose() });
  }

  const saving = create.isPending || update.isPending;

  return (
    <Modal open onClose={onClose} title={contact ? "Изменить контакт" : "Добавить контакт"} size="max-w-2xl">
      <form onSubmit={handleSave} className="my-2">
        <h2 className={`type-card-title ${C.color.text} mb-5`}>
          {contact ? "Изменить контакт" : "Добавить контакт"}
        </h2>

        <div className="space-y-4">
          {/* Name row 1 */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Фамилия" value={form.last_name} onChange={(v) => patch("last_name", v)} />
            <Field label="Имя *" required value={form.first_name} onChange={(v) => patch("first_name", v)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Отчество" value={form.middle_name} onChange={(v) => patch("middle_name", v)} />
            <Field label="Должность" value={form.title} onChange={(v) => patch("title", v)} placeholder="Категорийный менеджер" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Компания" value={form.company} onChange={(v) => patch("company", v)} hint="Только UI — не сохраняется на бэке v1" />
            <Field label="Подразделение" value={form.department} onChange={(v) => patch("department", v)} hint="Только UI — не сохраняется на бэке v1" />
          </div>

          {/* Phone + Email */}
          <div className="grid grid-cols-2 gap-3">
            <FieldWithIcon
              label="Телефон"
              value={form.phone}
              onChange={(v) => patch("phone", v)}
              icon={<Phone size={13} className={C.color.muted} />}
              placeholder="+7 (999) 000-00-00"
              type="tel"
            />
            <FieldWithIcon
              label="Email"
              value={form.email}
              onChange={(v) => patch("email", v)}
              icon={<Mail size={13} className={C.color.muted} />}
              placeholder="ivan@example.com"
              type="email"
            />
          </div>

          {/* Social media section */}
          <div className="pt-3 border-t border-brand-border">
            <p className="type-caption text-brand-muted mb-3">
              Социальные сети
            </p>
            <div className="grid grid-cols-2 gap-3">
              <FieldWithIcon
                label="LinkedIn"
                value={form.linkedin_url}
                onChange={(v) => patch("linkedin_url", v)}
                icon={<Linkedin size={13} className={C.color.muted} />}
                placeholder="https://linkedin.com/in/…"
                type="url"
              />
              <FieldWithIcon
                label="Telegram"
                value={form.telegram_url}
                onChange={(v) => patch("telegram_url", v)}
                icon={<TgSend size={13} className={C.color.muted} />}
                placeholder="https://t.me/…"
                type="url"
              />
            </div>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <FieldWithIcon
                label="Instagram"
                value={form.instagram_url}
                onChange={(v) => patch("instagram_url", v)}
                icon={<Instagram size={13} className={C.color.muted} />}
                placeholder="https://instagram.com/…"
                type="url"
                hint="Только UI — не сохраняется на бэке v1"
              />
              <FieldWithIcon
                label="Facebook"
                value={form.facebook_url}
                onChange={(v) => patch("facebook_url", v)}
                icon={<Facebook size={13} className={C.color.muted} />}
                placeholder="https://facebook.com/…"
                type="url"
                hint="Только UI — не сохраняется на бэке v1"
              />
            </div>
          </div>

          {/* Verification section */}
          <div className="pt-3 border-t border-brand-border">
            <p className="type-caption text-brand-muted mb-2">
              Верификация
            </p>
            <div className="flex gap-1.5 bg-brand-panel p-1 rounded-full w-fit">
              {(["high", "medium", "low"] as const).map((c) => {
                const isActive = form.confidence === c;
                const label = c === "high" ? "High" : c === "medium" ? "Medium" : "Не проверен";
                return (
                  <button
                    key={c}
                    type="button"
                    onClick={() => {
                      patch("confidence", c);
                      patch("verified_status", c === "low" ? "to_verify" : "verified");
                    }}
                    className={`px-3 py-1 type-caption font-semibold rounded-full transition-colors ${
                      isActive
                        ? "bg-white text-brand-accent-text"
                        : `${C.color.muted}`
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="type-caption text-brand-muted block mb-1.5">
              Заметки
            </label>
            <textarea
              value={form.notes}
              onChange={(e) => patch("notes", e.target.value)}
              rows={2}
              className="w-full px-3 py-2 type-caption text-brand-muted bg-white border border-brand-border rounded-xl outline-none focus:border-brand-accent transition-colors resize-none"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-brand-border">
          {contact ? (
            confirmDelete ? (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={del.isPending}
                  className="px-3 py-1.5 type-body font-semibold bg-rose text-white rounded-full transition-opacity"
                >
                  {del.isPending ? "Удаление…" : "Точно удалить"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmDelete(false)}
                  className={`px-3 py-1.5 type-body font-semibold ${C.color.muted}`}
                >
                  Отмена
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-semibold text-rose hover:bg-rose/10 rounded-full transition-colors"
              >
                <Trash2 size={13} />
                Удалить контакт
              </button>
            )
          ) : (
            <span />
          )}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className={`px-4 py-1.5 type-body font-semibold ${C.button.ghost}`}
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={saving || !form.first_name.trim()}
              className="px-4 py-1.5 type-body font-semibold bg-brand-accent text-white rounded-full disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
            >
              {saving ? "Сохранение…" : "Сохранить"}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  required,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
  hint?: string;
}) {
  return (
    <div>
      <label className="type-caption text-brand-muted block mb-1.5">
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className="w-full px-3 py-2 type-caption text-brand-muted bg-white border border-brand-border rounded-xl outline-none focus:border-brand-accent transition-colors"
      />
      {hint && (
        <p className="type-hint text-brand-muted mt-1">{hint}</p>
      )}
    </div>
  );
}

function FieldWithIcon({
  label,
  value,
  onChange,
  icon,
  placeholder,
  type = "text",
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  icon: React.ReactNode;
  placeholder?: string;
  type?: string;
  hint?: string;
}) {
  return (
    <div>
      <label className="type-caption text-brand-muted block mb-1.5">
        {label}
      </label>
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
          {icon}
        </span>
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full pl-9 pr-3 py-2 type-caption text-brand-muted bg-white border border-brand-border rounded-xl outline-none focus:border-brand-accent transition-colors"
        />
      </div>
      {hint && (
        <p className="type-hint text-brand-muted mt-1">{hint}</p>
      )}
    </div>
  );
}
