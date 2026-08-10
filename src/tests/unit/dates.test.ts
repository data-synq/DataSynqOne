import { describe, expect, it } from "vitest";

import { formatDaysUntil } from "../../src/utils/dates";

describe("formatDaysUntil", () => {
  it.each([
    [-2, "2 Tage über"],
    [-1, "1 Tag über"],
    [0, "heute"],
    [1, "morgen"],
    [8, "in 8 Tagen"],
  ])("formats %s days as %s", (days, expected) => {
    expect(formatDaysUntil(days)).toBe(expected);
  });
});
