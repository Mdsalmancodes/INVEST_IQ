import { z } from "zod";

/**
 * Alert form schemas — must match the backend's Pydantic DTOs exactly
 * (apps/core-api/src/presentation/dto/alert_dto.py) so client-side
 * validation never accepts something the server will reject.
 * `condition_type` mirrors the DB's ck_alerts_condition_type CHECK
 * constraint (migration 0005_alerts_context.py) exactly. `threshold` is
 * validated as a decimal string (never z.number()), matching
 * portfolio.ts's documented rationale for avoiding float rounding and
 * preserving backend Decimal discipline end-to-end.
 */

export const CONDITION_TYPES = [
  "price_above",
  "price_below",
  "pct_change",
  "rsi_threshold",
] as const;
export type ConditionTypeValue = (typeof CONDITION_TYPES)[number];

const DECIMAL_STRING_PATTERN = /^-?\d+(\.\d+)?$/;

const thresholdSchema = z
  .string()
  .trim()
  .min(1, "Threshold is required")
  .regex(DECIMAL_STRING_PATTERN, "Threshold must be a valid number");

export const createAlertSchema = z.object({
  symbol: z
    .string()
    .trim()
    .min(1, "A symbol is required")
    .max(20, "Symbol is too long")
    .transform((val) => val.toUpperCase()),
  conditionType: z.enum(CONDITION_TYPES),
  threshold: thresholdSchema,
  isRecurring: z.boolean().default(false),
  cooldownMinutes: z.number().int().min(0, "Cooldown cannot be negative").default(0),
});
export type CreateAlertFormValues = z.infer<typeof createAlertSchema>;

export const updateAlertSchema = z.object({
  conditionType: z.enum(CONDITION_TYPES).optional(),
  threshold: thresholdSchema.optional(),
  isRecurring: z.boolean().optional(),
  cooldownMinutes: z.number().int().min(0, "Cooldown cannot be negative").optional(),
  isActive: z.boolean().optional(),
});
export type UpdateAlertFormValues = z.infer<typeof updateAlertSchema>;
