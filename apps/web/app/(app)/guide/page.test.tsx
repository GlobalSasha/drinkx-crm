import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Руководство обязано совпадать с тем, что человек реально может сделать.
// Каждая проверка ниже закрывает конкретное расхождение, найденное 21.09.2026
// при сверке страницы с кодом — чтобы правку нельзя было молча откатить.

const { meMock } = vi.hoisted(() => ({ meMock: vi.fn() }));
vi.mock("@/lib/hooks/use-me", () => ({
  useMe: () => meMock(),
}));

import GuidePage from "./page";

function renderAs(role: "manager" | "head" | "admin") {
  meMock.mockReturnValue({ data: { id: "me-1", role } });
  render(<GuidePage />);
}

/** Весь видимый текст страницы одной строкой — руководство это проза, а не виджеты. */
function pageText(): string {
  return document.body.textContent ?? "";
}

describe("Руководство — версия менеджера", () => {
  afterEach(() => {
    meMock.mockReset();
    document.body.innerHTML = "";
  });

  it("не отправляет менеджера в базу лидов — брать оттуда он не может", () => {
    // Доступ урезан 14.09.2026 (PR #180): пункта нет в меню, GET /leads/pool
    // отдаёт 403, а claim упирается в стража роутера.
    renderAs("manager");
    const text = pageText();

    expect(text).not.toContain("Взять в работу");
    expect(text).toContain("Новых клиентов раздаёт руководитель");
  });

  it("оставляет возврат лида — вернуть менеджер по-прежнему может", () => {
    // Асимметрия намеренная: unclaim открыт владельцу лида.
    renderAs("manager");
    expect(pageText()).toContain("Вернуть в базу");
  });

  it("называет этап, на котором реально срабатывает гейт", () => {
    // check_economic_buyer_for_stage_6_plus: позиция >= 6 = «Договор / пилот».
    // «Multi-stakeholder» — позиция 5, гейта там нет.
    //
    // Проверяем саму фразу, а не просто наличие названия: «Договор / пилот»
    // встречается ещё и в списке из двенадцати этапов, поэтому поиск по одному
    // названию проходил бы при любом тексте плашки.
    renderAs("manager");
    const text = pageText();

    expect(text).toContain("Начиная с этапа «Договор / пилот» система попросит");
    expect(text).not.toContain("Начиная с этапа «Multi-stakeholder»");
  });

  it("не обещает запрет там, где гейт мягкий", () => {
    // Гейт объявлен hard=False — он всегда пропускает, спросив причину.
    renderAs("manager");
    expect(pageText()).toContain("спросит причину");
  });

  it("предупреждает, что две таблицы прогноза ему не покажут", () => {
    // /leads/utm-stats и /leads/stage-dwell закрыты require_admin_or_head.
    renderAs("manager");
    const text = pageText();

    expect(text).toContain("только по вашим сделкам");
    expect(text).toContain("показываются только руководителю");
  });

  it("не описывает почту в «Мессенджерах» — её там нет", () => {
    // /triage — Telegram, MAX, звонки. Ручной разбор писем отключён в Sprint 3.7.
    renderAs("manager");
    expect(pageText()).not.toContain("Почта, Telegram, MAX, звонки");
  });
});

describe("Руководство — версия руководителя", () => {
  afterEach(() => {
    meMock.mockReset();
    document.body.innerHTML = "";
  });

  it("открывается сразу на версии руководителя", () => {
    renderAs("head");
    expect(pageText()).toContain("Как вести команду");
  });

  it("не обещает сценарии прогноза — их нет ни в API, ни на странице", () => {
    // Домен quotas — только models.py, ни роутеров, ни блока сценариев.
    renderAs("head");
    expect(pageText()).not.toContain("сценари");
  });

  it("показывает руководителю обе таблицы прогноза", () => {
    renderAs("head");
    const text = pageText();

    expect(text).toContain("Каналы привлечения");
    expect(text).toContain("Где застревают сделки");
  });

  it("админ видит версию руководителя, а не менеджера", () => {
    renderAs("admin");
    expect(pageText()).toContain("Как вести команду");
  });
});
