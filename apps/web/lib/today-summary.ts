/**
 * Одна-две фразы сводки под приветствием на /today.
 *
 * Чистые функции: на вход — уже посчитанные цифры, на выход — текст и
 * «с чего начать». Никаких советов и догадок: только то, что есть в данных
 * (задачи ставят люди, см. docs/TASK_LISTS.md).
 */

export type DayPart = "morning" | "day" | "evening" | "night";

export function dayPart(hour: number): DayPart {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 18) return "day";
  if (hour >= 18) return "evening";
  return "night";
}

export const GREETING: Record<DayPart, string> = {
  morning: "Доброе утро",
  day: "Добрый день",
  evening: "Добрый вечер",
  night: "Доброй ночи",
};

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

/** Лид, с которого стоит начать: первая просроченная задача, иначе сегодняшняя, иначе протухающий лид. */
export interface FocusLead {
  id: string;
  name: string;
}

export interface ManagerDay {
  dueToday: number;
  overdue: number;
  rotting: number;
  focus: FocusLead | null;
}

export function managerSummary(d: ManagerDay, part: DayPart): string {
  const start = d.focus ? ` Начните с «${d.focus.name}».` : "";

  if (part === "evening" || part === "night") {
    if (d.dueToday === 0 && d.overdue === 0) {
      const tomorrow = d.focus ? ` Завтра начните с «${d.focus.name}».` : "";
      return `Задачи на сегодня закрыты.${tomorrow}`;
    }
    const left = d.dueToday + d.overdue;
    return `Осталось ${left} ${plural(left, "задача", "задачи", "задач")} — закройте или перенесите на завтра.`;
  }

  const parts: string[] = [];
  if (d.dueToday > 0) {
    parts.push(`На сегодня ${d.dueToday} ${plural(d.dueToday, "задача", "задачи", "задач")}`);
  }
  if (d.overdue > 0) {
    // «2 просрочены» читается только после «N задач»; без него нужно существительное.
    const noun = d.dueToday > 0 ? "" : ` ${plural(d.overdue, "задача", "задачи", "задач")}`;
    parts.push(`${d.overdue}${noun} ${plural(d.overdue, "просрочена", "просрочены", "просрочено")}`);
  }
  if (d.rotting > 0) {
    parts.push(`${d.rotting} ${plural(d.rotting, "лид протухает", "лида протухают", "лидов протухают")}`);
  }
  if (parts.length === 0) {
    return "На сегодня всё спокойно: просрочек нет, протухающих лидов нет.";
  }
  const sentence = parts.join(", ");
  return `${sentence[0].toUpperCase()}${sentence.slice(1)}.${start}`;
}

export interface HeadDay {
  leadsToday: number | null;
  leadsYesterday: number | null;
  stuck: number | null;
  /** Первый менеджер, который давно не заходил. */
  silent: { name: string; days: number } | null;
}

export function headSummary(d: HeadDay): string {
  const out: string[] = [];
  if (d.leadsToday != null) {
    const y = d.leadsYesterday != null ? ` (вчера ${d.leadsYesterday})` : "";
    out.push(`Сегодня ${d.leadsToday} ${plural(d.leadsToday, "новая заявка", "новые заявки", "новых заявок")}${y}.`);
  }
  if (d.stuck) {
    out.push(`${d.stuck} ${plural(d.stuck, "сделка застряла", "сделки застряли", "сделок застряли")} больше 7 дней.`);
  }
  if (d.silent) {
    out.push(`${d.silent.name} не заходит ${d.silent.days} ${plural(d.silent.days, "день", "дня", "дней")}.`);
  }
  return out.length ? out.join(" ") : "Команда на месте, срочного нет.";
}
