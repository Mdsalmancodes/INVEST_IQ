import { describe, expect, it } from "vitest";

import { updateNotificationPreferencesSchema } from "./notifications";

describe("updateNotificationPreferencesSchema", () => {
  it("accepts an empty object (all fields optional)", () => {
    const result = updateNotificationPreferencesSchema.safeParse({});
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.clearQuietHours).toBe(false);
    }
  });

  it("accepts toggling email and push alerts", () => {
    const result = updateNotificationPreferencesSchema.safeParse({
      priceAlertsEmail: false,
      priceAlertsPush: true,
    });
    expect(result.success).toBe(true);
  });

  it("accepts all valid digest frequencies", () => {
    for (const digestFrequency of ["off", "daily", "weekly"]) {
      expect(
        updateNotificationPreferencesSchema.safeParse({ digestFrequency }).success
      ).toBe(true);
    }
  });

  it("rejects an invalid digest frequency", () => {
    const result = updateNotificationPreferencesSchema.safeParse({
      digestFrequency: "hourly",
    });
    expect(result.success).toBe(false);
  });

  it("accepts valid quiet hours provided together", () => {
    const result = updateNotificationPreferencesSchema.safeParse({
      quietHoursStart: "22:00",
      quietHoursEnd: "07:00",
    });
    expect(result.success).toBe(true);
  });

  it("rejects quiet hours start without end", () => {
    const result = updateNotificationPreferencesSchema.safeParse({
      quietHoursStart: "22:00",
    });
    expect(result.success).toBe(false);
  });

  it("rejects an invalid time format", () => {
    const result = updateNotificationPreferencesSchema.safeParse({
      quietHoursStart: "25:99",
      quietHoursEnd: "07:00",
    });
    expect(result.success).toBe(false);
  });

  it("accepts clearQuietHours alone", () => {
    const result = updateNotificationPreferencesSchema.safeParse({ clearQuietHours: true });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.clearQuietHours).toBe(true);
    }
  });
});
