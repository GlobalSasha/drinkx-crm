"use client";
import { useState } from "react";
import {
  Plus,
  Trash2,
  Edit2,
  Mail,
  Phone,
  Send,
  Linkedin,
  AlertTriangle,
  Check,
  X,
} from "lucide-react";
import {
  useContacts,
  useCreateContact,
  useUpdateContact,
  useDeleteContact,
  useVerifyContact,
} from "@/lib/hooks/use-contacts";
import type {
  ContactOut,
  ContactCreate,
  ContactRoleType,
  LeadOut,
} from "@/lib/types";

const ROLE_LABELS: Record<ContactRoleType, string> = {
  economic_buyer: "Economic Buyer",
  champion: "Champion",
  technical: "Technical",
  operational: "Operational",
};

const ROLE_ORDER: ContactRoleType[] = [
  "economic_buyer",
  "champion",
  "technical",
  "operational",
];

const VERIFIED_COLORS: Record<string, string> = {
  verified: "bg-success/10 text-success",
  to_verify: "bg-warning/10 text-warning",
  invalid: "bg-rose/10 text-rose",
};

const VERIFIED_LABELS: Record<string, string> = {
  verified: "Верифицирован",
  to_verify: "Не проверен",
  invalid: "Недействителен",
};

const CONFIDENCE_COLORS: Record<string, string> = {
  high: "bg-success/10 text-success",
  medium: "bg-warning/10 text-warning",
  low: "bg-rose/10 text-rose",
};

const EMPTY_FORM: ContactCreate = {
  name: "",
  title: null,
  role_type: null,
  email: null,
  phone: null,
  telegram_url: null,
  linkedin_url: null,
  source: null,
  confidence: "medium",
  verified_status: "to_verify",
  notes: null,
};

interface Props {
  lead: LeadOut;
}

export function ContactsTab({ lead }: Props) {
  const { data: contacts = [], isLoading } = useContacts(lead.id);
  const createContact = useCreateContact(lead.id);
  const deleteContact = useDeleteContact(lead.id);
  const verifyContact = useVerifyContact(lead.id);

  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ContactCreate>(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const updateContact = useUpdateContact(lead.id, editingId ?? "");

  // Get current stage position (approximate — stage may be null)
  const stagePosition = 0; // we don't have stage info here; ADR-012 banner uses lead directly

  const hasEconomicBuyer = contacts.some(
    (c) => c.role_type === "economic_buyer"
  );

  function handleAddSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return;
    createContact.mutate(
      { ...form, name: form.name.trim() },
      {
        onSuccess: () => {
          setShowAddForm(false);
          setForm(EMPTY_FORM);
        },
      }
    );
  }

  function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name?.trim() || !editingId) return;
    updateContact.mutate(
      { ...form },
      {
        onSuccess: () => {
          setEditingId(null);
          setForm(EMPTY_FORM);
        },
      }
    );
  }

  function startEdit(contact: ContactOut) {
    setEditingId(contact.id);
    setForm({
      name: contact.name,
      title: contact.title,
      role_type: contact.role_type,
      email: contact.email,
      phone: contact.phone,
      telegram_url: contact.telegram_url,
      linkedin_url: contact.linkedin_url,
      source: contact.source,
      confidence: contact.confidence,
      verified_status: contact.verified_status,
      notes: contact.notes,
    });
    setShowAddForm(false);
  }

  function cancelForm() {
    setShowAddForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function confirmDelete(id: string) {
    deleteContact.mutate(id, {
      onSuccess: () => setDeleteConfirmId(null),
    });
  }

  if (isLoading) {
    return (
      <div className="py-8 text-center text-sm text-muted-2">Загрузка...</div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ADR-012 banner */}
      {!hasEconomicBuyer && (
        <div className="flex items-start gap-2 bg-warning/5 border border-warning/20 rounded-xl px-4 py-3">
          <AlertTriangle size={15} className="text-warning shrink-0 mt-0.5" />
          <p className="text-sm text-warning">
            Economic Buyer обязателен для перехода на Stage 6+
          </p>
        </div>
      )}

      {/* Role buckets */}
      {ROLE_ORDER.map((role) => {
        const roleContacts = contacts.filter((c) => c.role_type === role);
        return (
          <div key={role}>
            <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 mb-2">
              {ROLE_LABELS[role]}
              <span className="ml-1.5 text-muted-3">({roleContacts.length})</span>
            </p>
            <div className="space-y-2">
              {roleContacts.map((contact) =>
                editingId === contact.id ? (
                  <ContactForm
                    key={contact.id}
                    form={form}
                    setForm={setForm}
                    onSubmit={handleEditSubmit}
                    onCancel={cancelForm}
                    isLoading={updateContact.isPending}
                    submitLabel="Сохранить"
                  />
                ) : (
                  <ContactCard
                    key={contact.id}
                    contact={contact}
                    onEdit={() => startEdit(contact)}
                    onDelete={() => setDeleteConfirmId(contact.id)}
                    deleteConfirm={deleteConfirmId === contact.id}
                    onDeleteConfirm={() => confirmDelete(contact.id)}
                    onDeleteCancel={() => setDeleteConfirmId(null)}
                    onVerify={() => verifyContact.mutate(contact.id)}
                    isVerifying={
                      verifyContact.isPending &&
                      verifyContact.variables === contact.id
                    }
                  />
                )
              )}
              {roleContacts.length === 0 && (
                <p className="text-xs text-muted-3 italic pl-1">Нет контактов</p>
              )}
            </div>
          </div>
        );
      })}

      {/* Add form or button */}
      {showAddForm ? (
        <ContactForm
          form={form}
          setForm={setForm}
          onSubmit={handleAddSubmit}
          onCancel={cancelForm}
          isLoading={createContact.isPending}
          submitLabel="Добавить"
        />
      ) : (
        !editingId && (
          <button
            onClick={() => {
              setShowAddForm(true);
              setEditingId(null);
            }}
            className="flex items-center gap-2 text-sm font-semibold text-accent hover:text-accent/80 transition-colors"
          >
            <Plus size={15} />
            Добавить ЛПР
          </button>
        )
      )}
    </div>
  );
}

function ContactCard({
  contact,
  onEdit,
  onDelete,
  deleteConfirm,
  onDeleteConfirm,
  onDeleteCancel,
  onVerify,
  isVerifying,
}: {
  contact: ContactOut;
  onEdit: () => void;
  onDelete: () => void;
  deleteConfirm: boolean;
  onDeleteConfirm: () => void;
  onDeleteCancel: () => void;
  onVerify: () => void;
  isVerifying: boolean;
}) {
  const isUnverified = contact.verified_status === "to_verify";
  const isAiSourced =
    isUnverified &&
    !!contact.source &&
    /linkedin|hh|сайт|ai|brave|web/i.test(contact.source);

  return (
    <div
      className={`rounded-xl p-3.5 group ${
        isUnverified
          ? "bg-warning/5 border border-warning/30"
          : "bg-canvas border border-black/5"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            {isUnverified && (
              <AlertTriangle
                size={13}
                className="text-warning shrink-0"
                aria-label="Требует проверки"
              />
            )}
            <p className="text-sm font-semibold text-ink truncate">{contact.name}</p>
          </div>
          {contact.title && (
            <p className="text-xs text-muted-2 mt-0.5">
              {contact.title}
              {isAiSourced && (
                <span className="ml-1.5 text-muted-3">· AI (требует проверки)</span>
              )}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={onEdit}
            className="p-1.5 rounded-lg hover:bg-black/5 text-muted transition-colors"
          >
            <Edit2 size={13} />
          </button>
          {deleteConfirm ? (
            <div className="flex items-center gap-1">
              <button
                onClick={onDeleteConfirm}
                className="p-1.5 rounded-lg bg-rose/10 text-rose hover:bg-rose/20 transition-colors"
              >
                <Check size={13} />
              </button>
              <button
                onClick={onDeleteCancel}
                className="p-1.5 rounded-lg hover:bg-black/5 text-muted transition-colors"
              >
                <X size={13} />
              </button>
            </div>
          ) : (
            <button
              onClick={onDelete}
              className="p-1.5 rounded-lg hover:bg-rose/10 text-muted hover:text-rose transition-colors"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Contact links */}
      <div className="flex flex-wrap gap-2 mt-2">
        {contact.email && (
          <a
            href={`mailto:${contact.email}`}
            className="flex items-center gap-1 text-xs text-muted-2 hover:text-accent transition-colors"
          >
            <Mail size={11} />
            {contact.email}
          </a>
        )}
        {contact.phone && (
          <a
            href={`tel:${contact.phone}`}
            className="flex items-center gap-1 text-xs text-muted-2 hover:text-accent transition-colors"
          >
            <Phone size={11} />
            {contact.phone}
          </a>
        )}
        {contact.telegram_url && (
          <a
            href={contact.telegram_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-muted-2 hover:text-accent transition-colors"
          >
            <Send size={11} />
            TG
          </a>
        )}
        {contact.linkedin_url && (
          <a
            href={contact.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-muted-2 hover:text-accent transition-colors"
          >
            <Linkedin size={11} />
            LI
          </a>
        )}
      </div>

      {/* Badges */}
      <div className="flex flex-wrap gap-1.5 mt-2">
        <span
          className={`text-[10px] font-semibold px-2 py-0.5 rounded-pill ${
            VERIFIED_COLORS[contact.verified_status] ?? ""
          }`}
        >
          {VERIFIED_LABELS[contact.verified_status] ?? contact.verified_status}
        </span>
        <span
          className={`text-[10px] font-semibold px-2 py-0.5 rounded-pill ${
            CONFIDENCE_COLORS[contact.confidence] ?? ""
          }`}
        >
          {contact.confidence}
        </span>
      </div>

      {contact.notes && (
        <p className="text-xs text-muted-2 mt-2 italic">{contact.notes}</p>
      )}

      {/* Inline confirm/delete actions for AI-sourced unverified contacts */}
      {isUnverified && (
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-warning/20">
          <button
            type="button"
            onClick={onVerify}
            disabled={isVerifying}
            className="text-xs font-semibold px-3 py-1.5 rounded-pill bg-success/10 text-success hover:bg-success/20 disabled:opacity-50 transition-colors"
          >
            {isVerifying ? "Подтверждаю…" : "Подтвердить"}
          </button>
          {deleteConfirm ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={onDeleteConfirm}
                className="text-xs font-semibold px-3 py-1.5 rounded-pill bg-rose/10 text-rose hover:bg-rose/20 transition-colors"
              >
                Точно удалить
              </button>
              <button
                type="button"
                onClick={onDeleteCancel}
                className="text-xs font-semibold px-3 py-1.5 rounded-pill text-muted hover:bg-black/5 transition-colors"
              >
                Отмена
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={onDelete}
              className="text-xs font-semibold px-3 py-1.5 rounded-pill text-muted hover:bg-rose/10 hover:text-rose transition-colors"
            >
              Удалить
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function ContactForm({
  form,
  setForm,
  onSubmit,
  onCancel,
  isLoading,
  submitLabel,
}: {
  form: ContactCreate;
  setForm: (f: ContactCreate) => void;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
  isLoading: boolean;
  submitLabel: string;
}) {
  function field(key: keyof ContactCreate, label: string, type = "text", placeholder = "") {
    return (
      <div>
        <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1">
          {label}
        </label>
        <input
          type={type}
          value={(form[key] as string) ?? ""}
          onChange={(e) =>
            setForm({ ...form, [key]: e.target.value || null })
          }
          placeholder={placeholder}
          className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
        />
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="bg-canvas border border-black/10 rounded-xl p-4 space-y-3"
    >
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1">
            Имя *
          </label>
          <input
            type="text"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Иван Иванов"
            className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
          />
        </div>
        <div>
          <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1">
            Должность
          </label>
          <input
            type="text"
            value={form.title ?? ""}
            onChange={(e) => setForm({ ...form, title: e.target.value || null })}
            placeholder="Генеральный директор"
            className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
          />
        </div>
      </div>

      <div>
        <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1">
          Роль
        </label>
        <select
          value={form.role_type ?? ""}
          onChange={(e) =>
            setForm({
              ...form,
              role_type: (e.target.value as ContactRoleType) || null,
            })
          }
          className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
        >
          <option value="">— не выбрано —</option>
          <option value="economic_buyer">Economic Buyer</option>
          <option value="champion">Champion</option>
          <option value="technical">Technical</option>
          <option value="operational">Operational</option>
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {field("email", "Email", "email", "ivan@example.com")}
        {field("phone", "Телефон", "tel", "+7 (999) 000-00-00")}
      </div>

      <div className="grid grid-cols-2 gap-3">
        {field("telegram_url", "Telegram URL", "url", "https://t.me/...")}
        {field("linkedin_url", "LinkedIn URL", "url", "https://linkedin.com/...")}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1">
            Уверенность
          </label>
          <select
            value={form.confidence ?? "medium"}
            onChange={(e) =>
              setForm({ ...form, confidence: e.target.value as "low" | "medium" | "high" })
            }
            className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
          >
            <option value="low">Низкая</option>
            <option value="medium">Средняя</option>
            <option value="high">Высокая</option>
          </select>
        </div>
        <div>
          <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1">
            Статус верификации
          </label>
          <select
            value={form.verified_status ?? "to_verify"}
            onChange={(e) =>
              setForm({
                ...form,
                verified_status: e.target.value as "to_verify" | "verified" | "invalid",
              })
            }
            className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-all"
          >
            <option value="to_verify">Не проверен</option>
            <option value="verified">Верифицирован</option>
            <option value="invalid">Недействителен</option>
          </select>
        </div>
      </div>

      <div>
        <label className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-3 block mb-1">
          Заметки
        </label>
        <textarea
          value={form.notes ?? ""}
          onChange={(e) => setForm({ ...form, notes: e.target.value || null })}
          rows={2}
          className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 resize-none transition-all"
        />
      </div>

      <div className="flex gap-2 justify-end pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-1.5 rounded-pill text-sm font-semibold text-muted bg-white border border-black/10 hover:bg-canvas transition-all"
        >
          Отмена
        </button>
        <button
          type="submit"
          disabled={isLoading}
          className="px-4 py-1.5 rounded-pill text-sm font-semibold bg-ink text-white hover:bg-ink/90 disabled:opacity-50 transition-all"
        >
          {isLoading ? "..." : submitLabel}
        </button>
      </div>
    </form>
  );
}
