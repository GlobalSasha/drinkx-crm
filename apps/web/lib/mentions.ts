// @-упоминания в комментариях к лиду. Кого уведомить, решает сервер по тому
// же правилу (apps/api/app/activity/mentions.py), здесь — подсказки и подсветка.

export type MentionPart = { text: string; mention: boolean };

/** Разбить текст на обычные куски и упоминания известных людей. */
export function splitMentions(text: string, names: string[]): MentionPart[] {
  const known = names
    .map((n) => n.trim())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (known.length === 0) return [{ text, mention: false }];

  const pattern = new RegExp(
    `(?<![\\p{L}\\p{N}_@])@(?:${known.join("|")})(?![\\p{L}\\p{N}_])`,
    "giu",
  );
  const parts: MentionPart[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ text: text.slice(last, start), mention: false });
    parts.push({ text: match[0], mention: true });
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), mention: false });
  return parts;
}

/** Если курсор стоит сразу за «@слово», вернуть начало «@» и само слово. */
export function activeMentionQuery(
  text: string,
  caret: number,
): { start: number; query: string } | null {
  const match = /(?:^|\s)@([\p{L}\p{N}_-]*)$/u.exec(text.slice(0, caret));
  if (!match) return null;
  return { start: caret - match[1].length - 1, query: match[1] };
}

/** Заменить набранное «@сло» полным именем и поставить курсор за пробелом. */
export function insertMention(
  text: string,
  start: number,
  caret: number,
  name: string,
): { text: string; caret: number } {
  const inserted = `@${name} `;
  return {
    text: text.slice(0, start) + inserted + text.slice(caret),
    caret: start + inserted.length,
  };
}

/** Вставить «@» в позицию курсора, отделив пробелом от предыдущего слова. */
export function insertAtCaret(
  text: string,
  caret: number,
): { text: string; caret: number } {
  const before = text.slice(0, caret);
  const inserted = before && !/\s$/.test(before) ? " @" : "@";
  return {
    text: before + inserted + text.slice(caret),
    caret: caret + inserted.length,
  };
}
