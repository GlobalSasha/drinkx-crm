import { describe, expect, it } from "vitest";
import {
  activeMentionQuery,
  insertAtCaret,
  insertMention,
  splitMentions,
} from "./mentions";

const NAMES = ["Кирилл", "Dmitriy Onischuk", "Влада"];

describe("splitMentions", () => {
  it("выделяет упоминание независимо от регистра", () => {
    expect(splitMentions("@кирилл, как дела?", NAMES)).toEqual([
      { text: "@кирилл", mention: true },
      { text: ", как дела?", mention: false },
    ]);
  });

  it("находит имя с пробелом", () => {
    expect(splitMentions("спроси @Dmitriy Onischuk", NAMES)[1]).toEqual({
      text: "@Dmitriy Onischuk",
      mention: true,
    });
  });

  it("не считает упоминанием почту, чужое слово и продолжение имени", () => {
    for (const text of ["a@Влада", "@Иван", "@Владами"]) {
      expect(splitMentions(text, NAMES)).toEqual([{ text, mention: false }]);
    }
  });
});

describe("activeMentionQuery", () => {
  it("срабатывает только сразу за @ в начале слова", () => {
    expect(activeMentionQuery("привет @Ки", 10)).toEqual({ start: 7, query: "Ки" });
    expect(activeMentionQuery("@", 1)).toEqual({ start: 0, query: "" });
    expect(activeMentionQuery("a@Ки", 4)).toBeNull();
    expect(activeMentionQuery("@Кирилл привет", 14)).toBeNull();
  });
});

describe("вставка", () => {
  it("заменяет набранное именем", () => {
    expect(insertMention("привет @Ки?", 7, 10, "Кирилл")).toEqual({
      text: "привет @Кирилл ?",
      caret: 15,
    });
  });

  it("отделяет @ пробелом от слова", () => {
    expect(insertAtCaret("вопрос", 6)).toEqual({ text: "вопрос @", caret: 8 });
    expect(insertAtCaret("", 0)).toEqual({ text: "@", caret: 1 });
  });
});
