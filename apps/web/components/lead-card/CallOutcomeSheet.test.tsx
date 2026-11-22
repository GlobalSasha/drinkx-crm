import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CallOutcomeSheet } from "./CallOutcomeSheet";
import { OUTCOME_PREFILL } from "@/lib/call-outcome";

describe("CallOutcomeSheet", () => {
  afterEach(cleanup);

  it("каждый ответ передаёт свой исход, «Не сейчас» закрывает", () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(<CallOutcomeSheet company="Кофейня" onPick={onPick} onClose={onClose} />);
    expect(screen.getByRole("dialog", { name: "Как прошёл звонок?" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Не дозвонился" }));
    expect(onPick).toHaveBeenCalledWith("no_answer");
    fireEvent.click(screen.getByRole("button", { name: "Не сейчас" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("«Перезвонить» ведёт в задачу, остальные — в заметку о звонке", () => {
    expect(OUTCOME_PREFILL.call_back.mode).toBe("task");
    expect(OUTCOME_PREFILL.reached.mode).toBe("call");
    expect(OUTCOME_PREFILL.no_answer.mode).toBe("call");
  });
});
