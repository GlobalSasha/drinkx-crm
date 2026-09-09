import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api-client";
import { apiErrorDetail } from "@/lib/api-error";

describe("apiErrorDetail", () => {
  it("detail-строка", () => {
    const err = new ApiError(400, { detail: "нельзя удалить последнего админа" });
    expect(apiErrorDetail(err, "fallback")).toBe("нельзя удалить последнего админа");
  });

  it("detail-объект с message", () => {
    const err = new ApiError(502, {
      detail: { code: "invite_send_failed", message: "попробуйте позже" },
    });
    expect(apiErrorDetail(err, "fallback")).toBe("попробуйте позже");
  });

  it("detail-массив (422) → fallback", () => {
    const err = new ApiError(422, {
      detail: [{ loc: ["body", "email"], msg: "invalid" }],
    });
    expect(apiErrorDetail(err, "fallback")).toBe("fallback");
  });

  it("не-ApiError → fallback", () => {
    expect(apiErrorDetail(new Error("boom"), "fallback")).toBe("fallback");
  });
});
