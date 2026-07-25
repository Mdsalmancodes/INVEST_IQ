import { z } from "zod";

/**
 * Notification preference form schema — must match the backend's Pydantic
 * DTO exactly (apps/core-api/src/presentation/dto/notification_dto.py).
 * `digestFrequency` mirrors the DB's ck_notification_prefs_digest CHECK
 * constraint (migration 0005_alerts_context.py) exactly. Quiet hours are
 * validated as "HH:MM" strings (native <input type="time"> format),
 * matching the backend's time.fromisoformat() parsing (which also accepts
 * bare HH:MM, not just HH:MM:SS).
 */

export const DIGEST_FREQUENCIES = ["off", "daily", "weekly"] as const;
export type DigestFrequencyValue = (typeof DIGEST_FREQUENCIES)[number];

const TIME_STRING_PATTERN = /^([01]\d|2[0-3]):([0-5]\d)$/;

const timeStringSchema = z
  .string()
  .trim()
  .regex(TIME_STRING_PATTERN, "Must be a valid time (HH:MM)");

export const updateNotificationPreferencesSchema = z
  .object({
    priceAlertsEmail: z.boolean().optional(),
    priceAlertsPush: z.boolean().optional(),
    digestFrequency: z.enum(DIGEST_FREQUENCIES).optional(),
    quietHoursStart: z.union([timeStringSchema, z.literal("")]).optional(),
    quietHoursEnd: z.union([timeStringSchema, z.literal("")]).optional(),
    clearQuietHours: z.boolean().default(false),
  })
  .refine(
    (data) => !(data.quietHoursStart && !data.quietHoursEnd) &&
      !(data.quietHoursEnd && !data.quietHoursStart),
    {
      message: "Both quiet hours start and end are required together",
      path: ["quietHoursEnd"],
    }
  );
export type UpdateNotificationPreferencesFormValues = z.infer<
  typeof updateNotificationPreferencesSchema
>;
