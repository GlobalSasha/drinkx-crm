import { Pencil, Power, Trash2 } from "lucide-react";

import { T } from "@/lib/design-system";
import type { AutomationOut } from "@/lib/types";

import { ACTION_LABELS, TRIGGER_LABELS } from "./types";

interface Props {
  items: AutomationOut[];
  isAdminOrHead: boolean;
  deletePending: boolean;
  onShowRuns: (a: AutomationOut) => void;
  onEdit: (a: AutomationOut) => void;
  onDelete: (a: AutomationOut) => void;
}

export function AutomationsTable({
  items,
  isAdminOrHead,
  deletePending,
  onShowRuns,
  onEdit,
  onDelete,
}: Props) {
  return (
    <div className="bg-white border border-brand-border rounded-card overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-brand-bg">
          <tr className={`text-left ${T.mono} uppercase text-brand-muted`}>
            <th className="px-4 py-2 font-semibold">Название</th>
            <th className="px-4 py-2 font-semibold">Триггер</th>
            <th className="px-4 py-2 font-semibold">Действие</th>
            <th className="px-4 py-2 font-semibold">Статус</th>
            {isAdminOrHead && (
              <th className="px-4 py-2 font-semibold text-right">
                Действия
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr
              key={a.id}
              className="border-t border-brand-border hover:bg-brand-bg/40 transition-colors"
            >
              <td className="px-4 py-3 font-semibold text-brand-primary">
                <button
                  type="button"
                  onClick={() => onShowRuns(a)}
                  className="hover:text-brand-accent text-left"
                  title="Показать историю запусков"
                >
                  {a.name}
                </button>
              </td>
              <td className="px-4 py-3 text-xs text-brand-muted">
                {TRIGGER_LABELS[a.trigger]}
              </td>
              <td className="px-4 py-3 text-xs text-brand-muted">
                {ACTION_LABELS[a.action_type]}
              </td>
              <td className="px-4 py-3 text-xs">
                {a.is_active ? (
                  <span className="inline-flex items-center gap-1 text-success font-semibold">
                    <Power size={11} />
                    Активна
                  </span>
                ) : (
                  <span className="text-brand-muted">Выключена</span>
                )}
              </td>
              {isAdminOrHead && (
                <td className="px-4 py-3 text-right">
                  <div className="inline-flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => onEdit(a)}
                      className="text-brand-muted hover:text-brand-primary p-1.5 rounded-md hover:bg-black/5 transition-colors"
                      title="Редактировать"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(a)}
                      disabled={deletePending}
                      className="text-brand-muted hover:text-rose p-1.5 rounded-md hover:bg-rose/5 transition-colors disabled:opacity-40"
                      title="Удалить"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
