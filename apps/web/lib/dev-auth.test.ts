/**
 * DEV-FIX-03: обход входа включается только явным флагом и только вне
 * production. Уберите проверку `NODE_ENV` — красным станет случай (b).
 */
import { describe, expect, it } from "vitest";

import { isDevAuthBypass } from "./dev-auth";

describe("isDevAuthBypass", () => {
  it("(a) флаг в development — обход включён", () => {
    expect(isDevAuthBypass("1", "development")).toBe(true);
    expect(isDevAuthBypass("1", "test")).toBe(true);
  });

  it("(b) тот же флаг в production — обхода нет", () => {
    expect(isDevAuthBypass("1", "production")).toBe(false);
  });

  it("(c) без флага обхода нет нигде", () => {
    for (const env of ["development", "test", "production", undefined]) {
      expect(isDevAuthBypass(undefined, env)).toBe(false);
      expect(isDevAuthBypass("", env)).toBe(false);
      // Ровно "1", а не любое «похожее на да».
      expect(isDevAuthBypass("true", env)).toBe(false);
      expect(isDevAuthBypass("0", env)).toBe(false);
    }
  });
});
