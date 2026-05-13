"use client";

// /settings/profile — manager edits their own first/last name, phone, and
// (URL-only for now) avatar. Email is read-only because it's tied to the
// Google OAuth identity. Name is stored as a single "Имя Фамилия" string
// in `users.name`; we split on the frontend so the UI feels like two fields.

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronLeft, Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import { T } from "@/lib/design-system";
import { useMe } from "@/lib/hooks/use-me";
import type { MeOut } from "@/lib/types";

const ROLE_LABEL: Record<string, string> = {
  admin: "Администратор",
  head: "Руководитель",
  manager: "Менеджер",
};

function formatFullDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatShortDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
  });
}

export default function ProfilePage() {
  const { data: me, isLoading } = useMe();
  const qc = useQueryClient();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    const parts = (me.name ?? "").trim().split(/\s+/);
    setFirstName(parts[0] ?? "");
    setLastName(parts.slice(1).join(" "));
    setPhone(me.phone ?? "");
  }, [me]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const name = [firstName.trim(), lastName.trim()].filter(Boolean).join(" ");
      await api.patch<MeOut>("/auth/me", {
        name,
        phone: phone.trim() || null,
      });
      await qc.invalidateQueries({ queryKey: ["me"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  if (isLoading || !me) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 size={20} className="animate-spin text-brand-muted" />
      </div>
    );
  }

  const initials =
    [firstName[0], lastName[0]].filter(Boolean).join("").toUpperCase() ||
    me.email[0]?.toUpperCase() ||
    "?";

  return (
    <div className="max-w-xl mx-auto px-4 sm:px-6 py-6">
      <Link
        href="/settings"
        className="inline-flex items-center gap-1 text-xs font-mono text-brand-muted hover:text-brand-primary mb-4 transition-colors"
      >
        <ChevronLeft size={12} />
        Назад к настройкам
      </Link>

      <h1 className={T.heading + " mb-6"}>Мой профиль</h1>

      <div className="bg-white border border-brand-border rounded-2xl p-6 mb-4">
        <div className="flex items-center gap-4 mb-6 pb-6 border-b border-brand-border">
          <div className="w-16 h-16 rounded-full bg-brand-soft flex items-center justify-center text-xl font-semibold text-brand-accent shrink-0 overflow-hidden">
            {me.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={me.avatar_url}
                alt=""
                className="w-full h-full object-cover"
              />
            ) : (
              initials
            )}
          </div>
          <div className="min-w-0">
            <p className={T.body + " font-semibold truncate"}>
              {me.name || "—"}
            </p>
            <p className={T.mono + " text-brand-muted mt-0.5 truncate"}>
              {me.email}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div>
            <label className={T.caption + " block mb-1.5"}>Имя</label>
            <input
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="Кирилл"
              className="w-full border border-brand-border rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:border-brand-accent transition-colors"
            />
          </div>
          <div>
            <label className={T.caption + " block mb-1.5"}>Фамилия</label>
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Вербицкий"
              className="w-full border border-brand-border rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:border-brand-accent transition-colors"
            />
          </div>
        </div>

        <div className="mb-4">
          <label className={T.caption + " block mb-1.5"}>Email</label>
          <input
            type="email"
            value={me.email}
            disabled
            className="w-full border border-brand-border rounded-xl px-3 py-2 text-sm bg-brand-bg text-brand-muted cursor-not-allowed"
          />
          <p className={T.mono + " text-brand-muted mt-1"}>
            Привязан к Google, не редактируется
          </p>
        </div>

        <div>
          <label className={T.caption + " block mb-1.5"}>Телефон</label>
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+7 (___) ___-__-__"
            className="w-full border border-brand-border rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:border-brand-accent transition-colors"
          />
        </div>
      </div>

      <div className="bg-white border border-brand-border rounded-2xl p-4 mb-4">
        <p className={T.caption + " mb-3"}>Информация об аккаунте</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <p className={T.mono + " text-brand-muted"}>Роль</p>
            <p className={T.body + " font-medium mt-0.5"}>
              {ROLE_LABEL[me.role] ?? me.role}
            </p>
          </div>
          <div>
            <p className={T.mono + " text-brand-muted"}>В системе с</p>
            <p className={T.body + " font-medium mt-0.5"}>
              {formatFullDate(me.created_at)}
            </p>
          </div>
          <div>
            <p className={T.mono + " text-brand-muted"}>Последний вход</p>
            <p className={T.body + " font-medium mt-0.5"}>
              {formatShortDate(me.last_login_at)}
            </p>
          </div>
        </div>
      </div>

      {error && (
        <p className="text-xs font-mono text-red-600 mb-3">{error}</p>
      )}

      <div className="flex justify-end gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="px-5 py-2 bg-brand-accent text-white rounded-pill text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-opacity"
        >
          {saved ? "Сохранено ✓" : saving ? "Сохранение…" : "Сохранить"}
        </button>
      </div>
    </div>
  );
}
