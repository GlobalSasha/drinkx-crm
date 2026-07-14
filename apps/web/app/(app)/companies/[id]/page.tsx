"use client";
import { use, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Building2,
  Phone,
  Mail,
  MapPin,
  Globe,
  Hash,
  AlertTriangle,
  Loader2,
  Pencil,
  Check,
  X,
  Plus,
  GitMerge,
  User as UserIcon,
  FileText,
  ChevronRight,
  Activity as ActivityIcon,
  Briefcase,
  Wallet,
} from "lucide-react";
import {
  useCompany,
  useUpdateCompany,
} from "@/lib/hooks/use-companies";
import { useCreateLead } from "@/lib/hooks/use-leads";
import { useMe } from "@/lib/hooks/use-me";
import { ApiError } from "@/lib/api-client";
import type { CompanyUpdate, CompanyLeadSummary } from "@/lib/types";
import { C } from "@/lib/design-system";
import { dealTypeLabel } from "@/lib/i18n";
import { STAGE_COLOR_FALLBACK } from "@/components/ui/Chart";
import { Modal } from "@/components/ui/Modal";
import { CompanyMergeModal } from "@/components/companies/CompanyMergeModal";

function formatRub(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return (
    new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value) +
    " ₽"
  );
}

function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
}

interface Props {
  params: Promise<{ id: string }>;
}

export default function CompanyCardPage({ params }: Props) {
  const { id } = use(params);
  const { data: company, isLoading, isError } = useCompany(id);
  const update = useUpdateCompany(id);
  const createLead = useCreateLead();
  const me = useMe().data;
  const [editField, setEditField] = useState<keyof CompanyUpdate | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [toast, setToast] = useState<string | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [reqOpen, setReqOpen] = useState(false);

  const pipelineSum = useMemo(
    () => (company?.leads ?? []).reduce((s, l) => s + (l.deal_amount ?? 0), 0),
    [company?.leads],
  );

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }

  function startEdit(field: keyof CompanyUpdate, value: string | null) {
    setEditField(field);
    setDraft(value ?? "");
  }

  function commit() {
    if (!editField) return;
    const body: CompanyUpdate = { [editField]: draft || null } as CompanyUpdate;
    update.mutate(body, {
      onSuccess: () => {
        setEditField(null);
        showToast("Сохранено");
      },
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409) {
          showToast("Дубль — измените имя или используйте merge");
        } else {
          showToast("Не удалось сохранить");
        }
      },
    });
  }

  function handleCreateLead() {
    if (!company) return;
    createLead.mutate(
      { company_name: company.name } as Parameters<typeof createLead.mutate>[0],
      {
        onSuccess: () => showToast("Лид создан"),
        onError: () => showToast("Не удалось создать лид"),
      },
    );
  }

  if (isLoading) {
    return (
      <div className="font-sans min-h-screen bg-brand-bg flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-brand-muted" />
      </div>
    );
  }
  if (isError || !company) {
    return (
      <div className="font-sans min-h-screen bg-brand-bg flex flex-col items-center justify-center gap-4">
        <AlertTriangle size={24} className="text-rose" />
        <p className="type-body text-rose">Компания не найдена</p>
        <Link href="/pipeline" className={`type-body ${C.color.accent}`}>
          ← К воронке
        </Link>
      </div>
    );
  }

  const isAdmin = me?.role === "admin";

  return (
    <div className="font-sans min-h-screen bg-brand-bg">
      <header className="sticky top-0 z-20 bg-white border-b border-brand-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center gap-3">
          <Link
            href="/pipeline"
            className="p-1.5 rounded-full text-brand-muted hover:bg-brand-panel transition-colors shrink-0"
            aria-label="Назад"
          >
            <ArrowLeft size={18} />
          </Link>
          <div className="flex-1 min-w-0">
            {editField === "name" ? (
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit();
                  if (e.key === "Escape") setEditField(null);
                }}
                autoFocus
                className="text-xl font-semibold tracking-tight text-brand-primary bg-transparent border-b-2 border-brand-accent outline-none w-full"
              />
            ) : (
              <h1
                className="text-xl font-semibold tracking-tight text-brand-primary cursor-text hover:text-brand-accent-text transition-colors truncate"
                onClick={() => startEdit("name", company.name)}
                title="Редактировать"
              >
                {company.name}
                {company.is_archived && (
                  <span className={`ml-2 type-caption ${C.color.muted}`}>
                    (архив)
                  </span>
                )}
              </h1>
            )}
            <div className="flex flex-wrap items-center gap-2 mt-1">
              {company.inn && (
                <span className={`type-caption font-mono ${C.color.muted} bg-brand-panel px-2 py-0.5 rounded-full`}>
                  ИНН {company.inn}
                </span>
              )}
              {company.primary_segment && (
                <span className={`type-caption ${C.color.muted} bg-brand-panel px-2 py-0.5 rounded-full`}>
                  {company.primary_segment}
                </span>
              )}
              {company.city && (
                <span className={`flex items-center gap-1 type-caption ${C.color.muted}`}>
                  <MapPin size={11} />
                  {company.city}
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setReqOpen(true)}
            aria-label="Реквизиты"
            className={`inline-flex items-center gap-1.5 px-3 sm:px-4 py-1.5 type-body font-semibold ${C.button.ghost}`}
          >
            <FileText size={13} />
            <span className="hidden sm:inline">Реквизиты</span>
          </button>
          <button
            type="button"
            onClick={handleCreateLead}
            disabled={createLead.isPending}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold bg-brand-accent text-white rounded-full disabled:opacity-50 transition hover:bg-brand-accent/90 active:scale-[0.96]"
          >
            <Plus size={13} />
            Создать лид
          </button>
          {isAdmin && (
            <button
              type="button"
              onClick={() => setMergeOpen(true)}
              aria-label="Объединить"
              className={`inline-flex items-center gap-1.5 px-3 sm:px-4 py-1.5 type-body font-semibold ${C.button.ghost}`}
            >
              <GitMerge size={13} />
              <span className="hidden sm:inline">Объединить</span>
            </button>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto w-full px-4 sm:px-6 py-6 space-y-4">
        {/* Snapshot — deal-centric stats at a glance */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Stat
            icon={<Briefcase size={13} />}
            label="Сделок"
            value={String(company.leads.length)}
          />
          <Stat
            icon={<Wallet size={13} />}
            label="Сумма пайплайна"
            value={formatRub(pipelineSum > 0 ? pipelineSum : null)}
          />
          <Stat
            icon={<UserIcon size={13} />}
            label="Контактов"
            value={String(company.contacts.length)}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Main — deals (manager · stage · amount), the reason you're here */}
          <section className="md:col-span-2 space-y-3">
            <h2 className={`type-card-title ${C.color.text}`}>
              Сделки{" "}
              <span className={`type-caption ${C.color.muted}`}>
                ({company.leads.length})
              </span>
            </h2>
            {company.leads.length === 0 ? (
              <div className="rounded-card border border-dashed border-brand-border bg-white p-8 text-center">
                <p className="type-body text-brand-muted">
                  Пока нет сделок с этой компанией.
                </p>
                <button
                  type="button"
                  onClick={handleCreateLead}
                  disabled={createLead.isPending}
                  className="mt-3 inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold bg-brand-accent text-white rounded-full disabled:opacity-50 transition hover:bg-brand-accent/90 active:scale-[0.98]"
                >
                  <Plus size={13} />
                  Создать лид
                </button>
              </div>
            ) : (
              <ul className="space-y-3">
                {company.leads.map((l) => (
                  <li key={l.id}>
                    <DealCard lead={l} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Side — contacts + recent activity */}
          <aside className="flex flex-col gap-4">
            <section className="bg-white rounded-card border border-brand-border p-5">
              <h2 className={`type-card-title ${C.color.text} mb-3`}>
                Контакты{" "}
                <span className={`type-caption ${C.color.muted}`}>
                  ({company.contacts.length})
                </span>
              </h2>
              {company.contacts.length === 0 ? (
                <p className="type-hint text-brand-muted">Нет контактов.</p>
              ) : (
                <ul className="space-y-2">
                  {company.contacts.map((c) => (
                    <li key={c.id} className="px-3 py-2 rounded-xl bg-brand-panel">
                      <p className={`type-body font-semibold ${C.color.text}`}>{c.name}</p>
                      {c.title && (
                        <p className={`type-caption ${C.color.muted}`}>{c.title}</p>
                      )}
                      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
                        {c.phone && (
                          <a href={`tel:${c.phone}`} className={`type-caption ${C.color.accent} tabular-nums`}>
                            {c.phone}
                          </a>
                        )}
                        {c.email && (
                          <a href={`mailto:${c.email}`} className={`type-caption ${C.color.accent} truncate`}>
                            {c.email}
                          </a>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="bg-white rounded-card border border-brand-border p-5">
              <h2 className={`type-card-title ${C.color.text} mb-3`}>
                Активность{" "}
                <span className={`type-caption ${C.color.muted}`}>
                  ({company.recent_activities.length})
                </span>
              </h2>
              {company.recent_activities.length === 0 ? (
                <p className="type-hint text-brand-muted">Пока пусто.</p>
              ) : (
                <ul className="space-y-2">
                  {company.recent_activities.map((a) => (
                    <li
                      key={a.id}
                      className="px-3 py-2 rounded-xl bg-brand-panel"
                    >
                      <p className={`font-mono type-caption ${C.color.muted} uppercase tracking-wider`}>
                        {a.type} · {formatDateShort(a.created_at)}
                      </p>
                      {a.subject && (
                        <p className={`type-caption ${C.color.text} mt-0.5 font-semibold truncate`}>
                          {a.subject}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>
        </div>
      </main>

      {/* Requisites — demoted out of the hero into a dialog */}
      <Modal
        open={reqOpen}
        onClose={() => setReqOpen(false)}
        title="Реквизиты"
        size="max-w-lg"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className={`type-card-title ${C.color.text}`}>Реквизиты</h2>
          <button
            type="button"
            onClick={() => setReqOpen(false)}
            className="p-1.5 rounded-full hover:bg-brand-panel text-brand-muted transition-colors"
            aria-label="Закрыть"
          >
            <X size={16} />
          </button>
        </div>
        <div>
          <DataRow
            icon={<Building2 size={14} />}
            label="Юр. имя"
            value={company.legal_name}
            onEdit={() => startEdit("legal_name", company.legal_name)}
            editing={editField === "legal_name"}
            draft={draft}
            setDraft={setDraft}
            commit={commit}
            cancel={() => setEditField(null)}
          />
          <DataRow
            icon={<Hash size={14} />}
            label="ИНН"
            value={company.inn}
            onEdit={() => startEdit("inn", company.inn)}
            editing={editField === "inn"}
            draft={draft}
            setDraft={setDraft}
            commit={commit}
            cancel={() => setEditField(null)}
          />
          <DataRow
            icon={<Hash size={14} />}
            label="КПП"
            value={company.kpp}
            onEdit={() => startEdit("kpp", company.kpp)}
            editing={editField === "kpp"}
            draft={draft}
            setDraft={setDraft}
            commit={commit}
            cancel={() => setEditField(null)}
          />
          <DataRow
            icon={<Globe size={14} />}
            label="Сайт"
            value={company.website}
            isLink={company.website ? company.website : undefined}
            onEdit={() => startEdit("website", company.website)}
            editing={editField === "website"}
            draft={draft}
            setDraft={setDraft}
            commit={commit}
            cancel={() => setEditField(null)}
          />
          <DataRow
            icon={<Phone size={14} />}
            label="Телефон"
            value={company.phone}
            onEdit={() => startEdit("phone", company.phone)}
            editing={editField === "phone"}
            draft={draft}
            setDraft={setDraft}
            commit={commit}
            cancel={() => setEditField(null)}
          />
          <DataRow
            icon={<Mail size={14} />}
            label="Email"
            value={company.email}
            onEdit={() => startEdit("email", company.email)}
            editing={editField === "email"}
            draft={draft}
            setDraft={setDraft}
            commit={commit}
            cancel={() => setEditField(null)}
          />
          <DataRow
            icon={<MapPin size={14} />}
            label="Адрес"
            value={company.address}
            onEdit={() => startEdit("address", company.address)}
            editing={editField === "address"}
            draft={draft}
            setDraft={setDraft}
            commit={commit}
            cancel={() => setEditField(null)}
          />
        </div>
      </Modal>

      {mergeOpen && (
        <CompanyMergeModal
          sourceId={company.id}
          sourceName={company.name}
          onClose={() => setMergeOpen(false)}
          onSuccess={() => showToast("Компания объединена")}
        />
      )}

      {toast && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-brand-primary text-white type-body font-semibold px-5 py-2.5 rounded-full z-50"
        >
          {toast}
        </div>
      )}
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-card border border-brand-border bg-white px-4 py-3">
      <div className={`flex items-center gap-1.5 type-caption ${C.color.muted}`}>
        <span className="shrink-0">{icon}</span>
        <span className="truncate">{label}</span>
      </div>
      <p className={`type-card-title ${C.color.text} mt-1 tabular-nums`}>{value}</p>
    </div>
  );
}

function DealCard({ lead }: { lead: CompanyLeadSummary }) {
  return (
    <Link
      href={`/leads/${lead.id}` as `/leads/${string}`}
      className="group block rounded-card border border-brand-border bg-white p-4 transition-colors hover:border-brand-accent/40"
    >
      <div className="flex items-center justify-between gap-3">
        <span
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-white text-xs font-semibold shrink-0"
          style={{ backgroundColor: lead.stage_color ?? STAGE_COLOR_FALLBACK }}
        >
          {lead.stage_name ?? "Без этапа"}
        </span>
        <ChevronRight
          size={16}
          className="text-brand-muted opacity-0 coarse:opacity-100 group-hover:opacity-100 transition-opacity shrink-0"
        />
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="type-hint text-brand-muted">Сумма сделки</p>
          <p className={`type-card-title ${C.color.text} tabular-nums`}>
            {formatRub(lead.deal_amount)}
          </p>
          {lead.deal_type && (
            <p className={`type-caption ${C.color.muted} mt-0.5`}>
              {dealTypeLabel(lead.deal_type)}
            </p>
          )}
        </div>
        <p className={`type-caption ${C.color.muted} tabular-nums text-right shrink-0`}>
          score {lead.score}/100
          {lead.fit_score != null && ` · AI ${lead.fit_score}/10`}
        </p>
      </div>

      <div className="mt-3 pt-3 border-t border-brand-border flex flex-wrap items-center gap-x-4 gap-y-1 type-caption text-brand-muted">
        <span className="inline-flex items-center gap-1 min-w-0">
          <UserIcon size={11} className="shrink-0" />
          <span className="truncate">{lead.manager_name ?? "Не назначен"}</span>
        </span>
        {lead.last_activity_at && (
          <span className="inline-flex items-center gap-1">
            <ActivityIcon size={11} className="text-success" />
            активность {formatDateShort(lead.last_activity_at)}
          </span>
        )}
      </div>
    </Link>
  );
}

function DataRow({
  icon,
  label,
  value,
  isLink,
  onEdit,
  editing,
  draft,
  setDraft,
  commit,
  cancel,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  isLink?: string;
  onEdit: () => void;
  editing: boolean;
  draft: string;
  setDraft: (v: string) => void;
  commit: () => void;
  cancel: () => void;
}) {
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-brand-border last:border-0 group">
      <span className={`shrink-0 ${C.color.muted}`}>{icon}</span>
      <span
        className={`font-mono type-caption uppercase tracking-wider ${C.color.muted} w-20 shrink-0`}
      >
        {label}
      </span>
      {editing ? (
        <div className="flex-1 flex items-center gap-1">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") {
                // Cancel just this field — don't let the keydown bubble to
                // the Modal's document-level Escape handler (closes the dialog).
                e.stopPropagation();
                cancel();
              }
            }}
            autoFocus
            className="flex-1 px-3 py-1 type-body bg-white border border-brand-accent rounded-xl outline-none"
          />
          <button
            type="button"
            onClick={commit}
            className="p-1.5 rounded-full bg-success/10 text-success hover:bg-success/20"
          >
            <Check size={13} />
          </button>
          <button
            type="button"
            onClick={cancel}
            className="p-1.5 rounded-full hover:bg-brand-panel text-brand-muted"
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <>
          <span
            className={`flex-1 ${value ? "type-body text-brand-primary" : "type-hint text-brand-muted"}`}
          >
            {value ? (
              isLink ? (
                <a
                  href={isLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`${C.color.accent} hover:underline`}
                >
                  {value}
                </a>
              ) : (
                value
              )
            ) : (
              "—"
            )}
          </span>
          <button
            type="button"
            onClick={onEdit}
            className={`p-1 rounded-full opacity-0 coarse:opacity-100 group-hover:opacity-100 hover:bg-brand-panel text-brand-muted transition-opacity`}
            aria-label="Редактировать"
          >
            <Pencil size={11} />
          </button>
        </>
      )}
    </div>
  );
}
