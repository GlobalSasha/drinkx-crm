import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedComposer } from "./FeedComposer";

const send = vi.fn().mockResolvedValue({});

vi.mock("@/lib/hooks/use-feed", () => ({
  useCreateActivity: () => ({ mutateAsync: send, isPending: false }),
}));
vi.mock("@/lib/hooks/use-task-files", () => ({
  useUploadLeadFile: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/lib/hooks/use-me", () => ({ useMe: () => ({ data: { id: "me" } }) }));
vi.mock("@/lib/hooks/use-lead", () => ({
  useLead: () => ({ data: { assigned_to: "vlada" } }),
}));
vi.mock("@/lib/hooks/use-users", () => ({
  useUsers: () => ({
    data: {
      items: [
        { id: "me", name: "Александр", role: "admin" },
        { id: "vlada", name: "Влада", role: "manager" },
        { id: "anton", name: "Антон", role: "manager" },
      ],
    },
  }),
}));

function field() {
  return screen.getByRole("combobox") as HTMLTextAreaElement;
}

function type(value: string) {
  fireEvent.change(field(), {
    target: { value, selectionStart: value.length, selectionEnd: value.length },
  });
}

describe("FeedComposer: @-упоминания", () => {
  beforeEach(() => {
    send.mockClear();
    window.localStorage.clear(); // drafts must not leak between tests
    render(<FeedComposer leadId="lead" />);
  });
  afterEach(cleanup);

  it("показывает коллег без автора и помечает того, кто не видит карточку", () => {
    type("@");
    const names = screen.getAllByRole("option").map((o) => o.textContent);
    expect(names).toEqual(["Влада", "Антонне видит эту карточку"]);
  });

  it("Enter выбирает человека, а не отправляет; следующий Enter отправляет", async () => {
    type("@Вл");
    fireEvent.keyDown(field(), { key: "Enter" });
    expect(send).not.toHaveBeenCalled();
    expect(field().value).toBe("@Влада ");

    type("@Влада вопрос");
    fireEvent.keyDown(field(), { key: "Enter" });
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith({ type: "comment", body: "@Влада вопрос" }),
    );
  });

  it("стрелка переводит выбор, Esc закрывает список", () => {
    type("@");
    fireEvent.keyDown(field(), { key: "ArrowDown" });
    fireEvent.keyDown(field(), { key: "Enter" });
    expect(field().value).toBe("@Антон ");

    type("@Антон @");
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("клик по имени и кнопка «Спросить коллегу»", () => {
    fireEvent.click(screen.getByRole("button", { name: "Спросить коллегу" }));
    expect(field().value).toBe("@");
    fireEvent.click(screen.getByText("Влада"));
    expect(field().value).toBe("@Влада ");
  });
});

describe("FeedComposer: телефон и черновик", () => {
  const originalMatchMedia = window.matchMedia;
  beforeEach(() => {
    send.mockReset();
    send.mockResolvedValue({});
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    window.matchMedia = originalMatchMedia;
  });

  it("на сенсорном экране Enter переносит строку, а не отправляет", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never;
    render(<FeedComposer leadId="lead" />);
    type("привет");
    fireEvent.keyDown(field(), { key: "Enter" });
    expect(send).not.toHaveBeenCalled();
  });

  it("несохранённый комментарий возвращается после повторного открытия", async () => {
    const first = render(<FeedComposer leadId="lead-d" />);
    type("перезвонить в пятницу");
    first.unmount();
    render(<FeedComposer leadId="lead-d" />);
    await waitFor(() => expect(field().value).toBe("перезвонить в пятницу"));
  });

  it("при ошибке отправки текст остаётся в поле", async () => {
    send.mockRejectedValueOnce(new Error("offline"));
    render(<FeedComposer leadId="lead-e" />);
    type("важно");
    fireEvent.keyDown(field(), { key: "Enter" });
    await waitFor(() => expect(send).toHaveBeenCalled());
    expect(field().value).toBe("важно");
  });

  it("исход звонка заполняет поле, но ничего не отправляет сам", async () => {
    render(<FeedComposer leadId="lead-g" modeRequest="call" prefillText="Не дозвонился" />);
    await waitFor(() => expect(field().value).toBe("Не дозвонился"));
    expect(send).not.toHaveBeenCalled();
  });

  it("после успешной отправки черновик удаляется", async () => {
    render(<FeedComposer leadId="lead-f" />);
    type("готово");
    fireEvent.keyDown(field(), { key: "Enter" });
    await waitFor(() => expect(field().value).toBe(""));
    expect(window.localStorage.getItem("drinkx:comment-draft:lead-f")).toBeNull();
  });
});
