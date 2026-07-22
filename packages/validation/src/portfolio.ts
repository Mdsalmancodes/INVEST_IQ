import { z } from "zod";

/**
 * Portfolio/transaction form schemas — must match the backend's Pydantic
 * DTOs exactly (apps/core-api/src/presentation/dto/portfolio_dto.py) so
 * client-side validation never accepts something the server will reject.
 *
 * Money/quantity fields are validated as decimal STRINGS, never numbers —
 * matching the backend's Decimal-never-float discipline (Document 3 §3.4
 * rule #2) all the way to the client boundary. A native `z.number()` here
 * would round-trip through IEEE-754 floats even before the value reaches
 * the wire, defeating the purpose. React Hook Form text inputs naturally
 * produce strings, so this is also the more ergonomic fit, not just the
 * "correct" one.
 */

const decimalStringRegex = /^-?\d+(\.\d+)?$/;

export const decimalStringSchema = (fieldLabel: string) =>
  z
    .string()
    .trim()
    .min(1, `${fieldLabel} is required`)
    .regex(decimalStringRegex, `${fieldLabel} must be a valid decimal number`);

export const positiveDecimalStringSchema = (fieldLabel: string) =>
  decimalStringSchema(fieldLabel).refine((val) => Number.parseFloat(val) > 0, {
    message: `${fieldLabel} must be greater than 0`,
  });

export const nonNegativeDecimalStringSchema = (fieldLabel: string) =>
  decimalStringSchema(fieldLabel).refine((val) => Number.parseFloat(val) >= 0, {
    message: `${fieldLabel} cannot be negative`,
  });

export const CURRENCY_CODES = ["USD", "EUR", "GBP", "INR", "JPY"] as const;

export const createPortfolioSchema = z.object({
  name: z.string().trim().min(1, "Portfolio name is required").max(200, "Name is too long"),
  baseCurrency: z.enum(CURRENCY_CODES).default("USD"),
  isPaper: z.boolean().default(true),
});
export type CreatePortfolioFormValues = z.infer<typeof createPortfolioSchema>;

export const updatePortfolioSchema = z.object({
  name: z.string().trim().min(1, "Portfolio name is required").max(200, "Name is too long"),
  baseCurrency: z.enum(CURRENCY_CODES),
});
export type UpdatePortfolioFormValues = z.infer<typeof updatePortfolioSchema>;

/** Matches ADR-0003's 8 transaction types exactly. */
export const TRANSACTION_TYPES = [
  "buy",
  "sell",
  "dividend",
  "split",
  "transfer_in",
  "transfer_out",
  "deposit",
  "withdrawal",
] as const;
export type TransactionTypeValue = (typeof TRANSACTION_TYPES)[number];

const INSTRUMENT_REQUIRED_TYPES = new Set<TransactionTypeValue>([
  "buy",
  "sell",
  "dividend",
  "split",
  "transfer_in",
  "transfer_out",
]);

/**
 * A single discriminated schema (rather than 8 separate ones) so a form
 * can switch its validation rules reactively as the user picks a
 * transaction type, matching the backend's single-endpoint,
 * type-discriminated Transaction entity (Document 3 §3.4/ADR-0003) shape
 * for shape-for-shape client/server symmetry.
 */
export const addTransactionSchema = z
  .object({
    type: z.enum(TRANSACTION_TYPES),
    executedAt: z.string().min(1, "Execution date/time is required"),
    instrumentId: z.string().trim().optional(),
    quantity: z.string().trim().optional(),
    price: z.string().trim().optional(),
    fees: z.string().trim().optional().default("0"),
    splitRatio: z.string().trim().optional(),
    relatedPortfolioId: z.string().trim().optional(),
    cashAmount: z.string().trim().optional(),
  })
  .superRefine((data, ctx) => {
    const requiresInstrument = INSTRUMENT_REQUIRED_TYPES.has(data.type);
    if (requiresInstrument && !data.instrumentId) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["instrumentId"],
        message: "Instrument is required for this transaction type",
      });
    }

    if (data.type === "split") {
      if (!data.splitRatio || !decimalStringRegex.test(data.splitRatio)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["splitRatio"],
          message: "A valid split ratio is required (e.g. 2 for a 2:1 split)",
        });
      } else if (Number.parseFloat(data.splitRatio) <= 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["splitRatio"],
          message: "Split ratio must be greater than 0",
        });
      }
    } else if (["buy", "sell", "dividend", "transfer_in"].includes(data.type)) {
      if (!data.quantity || !decimalStringRegex.test(data.quantity)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["quantity"],
          message: "A valid quantity is required",
        });
      }
      if (!data.price || !decimalStringRegex.test(data.price)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["price"],
          message: "A valid price is required",
        });
      }
    } else if (data.type === "transfer_out") {
      if (!data.quantity || !decimalStringRegex.test(data.quantity)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["quantity"],
          message: "A valid quantity is required",
        });
      }
    } else if (data.type === "deposit" || data.type === "withdrawal") {
      if (!data.cashAmount || !decimalStringRegex.test(data.cashAmount)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["cashAmount"],
          message: "A valid cash amount is required",
        });
      }
    }
  });
export type AddTransactionFormValues = z.infer<typeof addTransactionSchema>;
