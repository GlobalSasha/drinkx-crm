"use client";

import { useEffect, useState } from "react";
import { CheckSquare, ChevronsRight, MessageSquare, Phone } from "lucide-react";
import { useContacts } from "@/lib/hooks/use-contacts";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import type { LeadOut, Stage } from "@/lib/types";

/** Phone to dial: the lead's primary contact, else the lead's own phone. */
export function pickCallPhone(
  lead: Pick<LeadOut, "phone" | "primary_contact_id">,
  contacts: { id: string; phone: string | null }[],
): string | null {
  const primary =
    contacts.find((c) => c.id === lead.primary_contact_id) ?? contacts[0];
  return primary?.phone || lead.phone || null;
}

/** True while the manager types into a field — the bar steps aside so it
 *  never covers the composer above the on-screen keyboard. */
function useEditingField(): boolean {
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    const isField = (el: EventTarget | null) =>
      el instanceof HTMLElement &&
      (el.tagName === "TEXTAREA" ||
        (el.tagName === "INPUT" &&
          !["checkbox", "radio", "button", "submit"].includes(
            (el as HTMLInputElement).type,
          )) ||
        el.isContentEditable);
    const onIn = (e: FocusEvent) => setEditing(isField(e.target));
    const onOut = () => setEditing(false);
    document.addEventListener("focusin", onIn);
    document.addEventListener("focusout", onOut);
    return () => {
      document.removeEventListener("focusin", onIn);
      document.removeEventListener("focusout", onOut);
    };
  }, []);
  return editing;
}

const ITEM =
  "flex-1 min-h-11 flex flex-col items-center justify-center gap-1 rounded-lg type-label text-brand-primary active:scale-[0.96] transition-transform disabled:opacity-40";

interface Props {
  lead: LeadOut;
  stages: Stage[];
  currentStageId: string | null | undefined;
  onComment: () => void;
  onTask: () => void;
  onStageSelect: (stage: Stage) => void;
}

/** Phone-only sticky action row: Позвонить · Комментарий · Задача · Стадия. */
export function MobileActionBar({
  lead,
  stages,
  currentStageId,
  onComment,
  onTask,
  onStageSelect,
}: Props) {
  const { data: contacts = [] } = useContacts(lead.id);
  const editing = useEditingField();
  const phone = pickCallPhone(lead, contacts);
  const openStages = stages.filter((s) => !s.is_won && !s.is_lost);

  if (editing) return null;

  return (
    <nav
      aria-label="Действия с лидом"
      className="md:hidden fixed inset-x-0 bottom-0 z-30 bg-white border-t border-brand-border px-2 pt-2"
      style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom))" }}
    >
      <div className="flex items-stretch gap-1">
        {phone ? (
          <a href={`tel:${phone}`} className={ITEM}>
            <Phone size={20} aria-hidden />
            Позвонить
          </a>
        ) : (
          <button type="button" disabled className={ITEM} title="Телефон не указан">
            <Phone size={20} aria-hidden />
            Позвонить
          </button>
        )}
        <button type="button" onClick={onComment} className={ITEM}>
          <MessageSquare size={20} aria-hidden />
          Комментарий
        </button>
        <button type="button" onClick={onTask} className={ITEM}>
          <CheckSquare size={20} aria-hidden />
          Задача
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className={ITEM} disabled={openStages.length === 0}>
              <ChevronsRight size={20} aria-hidden />
              Стадия
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="end" className="w-64">
            {openStages.map((s) => (
              <DropdownMenuItem
                key={s.id}
                disabled={s.id === currentStageId}
                onSelect={() => onStageSelect(s)}
                className="min-h-11"
              >
                {s.name}
                {s.id === currentStageId ? " · сейчас" : ""}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </nav>
  );
}
