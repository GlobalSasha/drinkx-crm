"use client";
import { use, useState } from "react";
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
} from "lucide-react";
import {
  useCompany,
  useUpdateCompany,
} from "@/lib/hooks/use-companies";
import { useCreateLead } from "@/lib/hooks/use-leads";
import { useMe } from "@/lib/hooks/use-me";
import { ApiError } from "@/lib/api-client";
import type { CompanyUpdate } from "@/lib/types";
import { C } from "@/lib/design-system";
import { CompanyMergeModal } from "@/components/companies/CompanyMergeModal";

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
      <div className="font-sans min-h-screen bg-canvas flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-brand-muted" />
      </div>
    );
  }
  if (isError || !company) {
    return (
      <div className="font-sans min-h-screen bg-canvas flex flex-col items-center justify-center gap-4">
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
    <div className="font-sans min-h-screen bg-canvas">
      <header className="sticky top-0 z-20 bg-white border-b border-brand-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center gap-3">
          <Link
            href="/pipeline"
            className="p-1.5 rounded-full text-brand-muted hover:bg-brand-panel transition-colors"
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
                className="text-xl font-semibold tracking-tight text-ink bg-transparent border-b-2 border-brand-accent outline-none w-full"
              />
            ) : (
              <h1
                className="text-xl font-semibold tracking-tight text-ink cursor-text hover:text-brand-accent-text transition-colors truncate"
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
            onClick={handleCreateLead}
            disabled={createLead.isPending}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold bg-brand-accent text-white rounded-full disabled:opacity-50 transition-opacity"
          >
            <Plus size={13} />
            Создать лид
          </button>
          {isAdmin && (
            <button
              type="button"
              onClick={() => setMergeOpen(true)}
              className={`inline-flex items-center gap-1.5 px-4 py-1.5 type-body font-semibold ${C.button.ghost} transition-opacity`}
            >
              <GitMerge size={13} />
              Объединить
            </button>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto w-full px-4 sm:px-6 py-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Left: data */}
        <section className="md:col-span-2 bg-white rounded-2xl border border-brand-border p-5">
          <h2 className={`type-card-title ${C.color.text} mb-4`}>
            Реквизиты
          </h2>
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
        </section>

        {/* Right: leads + contacts */}
        <aside className="flex flex-col gap-4">
          <section className="bg-white rounded-2xl border border-brand-border p-5">
            <h2 className={`type-card-title ${C.color.text} mb-3`}>
              Сделки <span className={`type-caption ${C.color.muted}`}>({company.leads.length})</span>
            </h2>
            {company.leads.length === 0 ? (
              <p className="type-hint text-brand-muted">Нет сделок.</p>
            ) : (
              <ul className="space-y-2">
                {company.leads.map((l) => (
                  <li key={l.id}>
                    <Link
                      href={`/leads/${l.id}` as `/leads/${string}`}
                      className={`block px-3 py-2 rounded-xl bg-brand-panel hover:bg-brand-bg transition-colors`}
                    >
                      <p className={`type-body font-semibold ${C.color.text} truncate`}>
                        {l.company_name}
                      </p>
                      <p className={`type-caption ${C.color.muted}`}>
                        score {l.score}/100
                        {l.fit_score != null && ` · AI ${l.fit_score}/10`}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="bg-white rounded-2xl border border-brand-border p-5">
            <h2 className={`type-card-title ${C.color.text} mb-3`}>
              Контакты <span className={`type-caption ${C.color.muted}`}>({company.contacts.length})</span>
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
                    <div className="flex gap-2 mt-1">
                      {c.phone && (
                        <a href={`tel:${c.phone}`} className={`type-caption ${C.color.accent}`}>
                          {c.phone}
                        </a>
                      )}
                      {c.email && (
                        <a href={`mailto:${c.email}`} className={`type-caption ${C.color.accent}`}>
                          {c.email}
                        </a>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="bg-white rounded-2xl border border-brand-border p-5">
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
                    className="type-caption text-brand-muted px-3 py-2 rounded-xl bg-brand-panel"
                  >
                    <p className={`font-mono ${C.color.muted} uppercase tracking-wider`}>
                      {a.type} · {new Date(a.created_at).toLocaleDateString("ru-RU")}
                    </p>
                    {a.subject && (
                      <p className={`${C.color.text} mt-0.5 font-semibold truncate`}>
                        {a.subject}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </main>

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
              if (e.key === "Escape") cancel();
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
            className={`flex-1 ${value ? "type-body text-ink" : "type-hint text-brand-muted"}`}
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
            className={`p-1 rounded-full opacity-0 group-hover:opacity-100 hover:bg-brand-panel text-brand-muted transition-opacity`}
            aria-label="Редактировать"
          >
            <Pencil size={11} />
          </button>
        </>
      )}
    </div>
  );
}
