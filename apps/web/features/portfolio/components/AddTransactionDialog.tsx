"use client";
import { marketDataApi } from "@/lib/market-data-api";
import { StockSearch } from "@/features/market-data/components/StockSearch";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@investiq/ui";
import {
  TRANSACTION_TYPES,
  type AddTransactionFormValues,
  addTransactionSchema,
} from "@investiq/validation";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../../../lib/auth-api";
import { useAddTransaction } from "../hooks/useTransactions";


export interface AddTransactionDialogProps {
  portfolioId: string;
  isOpen: boolean;
  onClose: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  buy: "Buy",
  sell: "Sell",
  dividend: "Dividend",
  split: "Split",
  transfer_in: "Transfer In",
  transfer_out: "Transfer Out",
  deposit: "Deposit",
  withdrawal: "Withdrawal",
};

const INSTRUMENT_REQUIRED = new Set(["buy", "sell", "dividend", "split", "transfer_in", "transfer_out"]);
const QUANTITY_PRICE_REQUIRED = new Set(["buy", "sell", "dividend", "transfer_in"]);

/**
 * AddTransactionDialog — a single form covering all 8 ADR-0003 transaction
 * types, showing only the fields relevant to the selected type (mirrors
 * the backend's per-type validation in
 * apps/core-api/src/domain/portfolio/entities.py Transaction._validate()).
 */
export function AddTransactionDialog({ portfolioId, isOpen, onClose }: AddTransactionDialogProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const addTransaction = useAddTransaction(portfolioId);
  const {
    register,
    handleSubmit,
    watch,
    reset,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<AddTransactionFormValues>({
    resolver: zodResolver(addTransactionSchema),
    defaultValues: { type: "buy", fees: "0" },
  });

  const selectedType = watch("type");

  if (!isOpen) return null;

  const onSubmit = async (values: AddTransactionFormValues) => {
    setServerError(null);
    try {
      await addTransaction.mutateAsync({
        type: values.type,
        executed_at: values.executedAt,
        instrument_id: values.instrumentId,
        quantity: values.quantity,
        price: values.price,
        fees: values.fees,
        split_ratio: values.splitRatio ? Number.parseFloat(values.splitRatio) : undefined,
        related_portfolio_id: values.relatedPortfolioId,
        cash_amount: values.cashAmount,
      });
      reset();
      onClose();
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Failed to add transaction.");
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-transaction-title"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          transition={{ duration: 0.2 }}
          className="w-full max-w-md rounded-lg bg-surface p-6 shadow-lg"
        >
          <h2 id="add-transaction-title" className="text-lg font-semibold text-text-primary">
            Add Transaction
          </h2>

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-4 flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="type" className="text-sm font-medium text-text-primary">
                Transaction Type
              </label>
              <select
                id="type"
                className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                {...register("type")}
              >
                {TRANSACTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {TYPE_LABELS[type]}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="executedAt" className="text-sm font-medium text-text-primary">
                Executed At
              </label>
              <input
                id="executedAt"
                type="datetime-local"
                className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                aria-invalid={errors.executedAt ? "true" : "false"}
                {...register("executedAt")}
              />
              {errors.executedAt && (
                <p role="alert" className="text-sm text-danger">
                  {errors.executedAt.message}
                </p>
              )}
            </div>

            {INSTRUMENT_REQUIRED.has(selectedType) && (
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-text-primary">
                  Select Stock
                </label>

                <StockSearch
                  onSelect={(instrument) => {
                    try {
                    
                    setValue("instrumentId", instrument.id, {
                      shouldValidate: true,
                      shouldDirty: true,
                    });

                  } catch (err) {
                    console.error("Failed to fetch instrument:", err);
                  }
                }}
              />
        

              {errors.instrumentId && (
                  <p role="alert" className="text-sm text-danger">
                    {errors.instrumentId.message}
                  </p>
                )}
              </div>
            )}

            {(QUANTITY_PRICE_REQUIRED.has(selectedType) || selectedType === "transfer_out") && (
              <div className="flex flex-col gap-1">
                <label htmlFor="quantity" className="text-sm font-medium text-text-primary">
                  Quantity
                </label>
                <input
                  id="quantity"
                  type="text"
                  inputMode="decimal"
                  className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                  aria-invalid={errors.quantity ? "true" : "false"}
                  {...register("quantity")}
                />
                {errors.quantity && (
                  <p role="alert" className="text-sm text-danger">
                    {errors.quantity.message}
                  </p>
                )}
              </div>
            )}

            {QUANTITY_PRICE_REQUIRED.has(selectedType) && (
              <div className="flex flex-col gap-1">
                <label htmlFor="price" className="text-sm font-medium text-text-primary">
                  Price per Share
                </label>
                <input
                  id="price"
                  type="text"
                  inputMode="decimal"
                  className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                  aria-invalid={errors.price ? "true" : "false"}
                  {...register("price")}
                />
                {errors.price && (
                  <p role="alert" className="text-sm text-danger">
                    {errors.price.message}
                  </p>
                )}
              </div>
            )}

            {selectedType === "split" && (
              <div className="flex flex-col gap-1">
                <label htmlFor="splitRatio" className="text-sm font-medium text-text-primary">
                  Split Ratio (e.g. 2 for a 2:1 split)
                </label>
                <input
                  id="splitRatio"
                  type="text"
                  inputMode="decimal"
                  className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                  aria-invalid={errors.splitRatio ? "true" : "false"}
                  {...register("splitRatio")}
                />
                {errors.splitRatio && (
                  <p role="alert" className="text-sm text-danger">
                    {errors.splitRatio.message}
                  </p>
                )}
              </div>
            )}

            {(selectedType === "deposit" || selectedType === "withdrawal") && (
              <div className="flex flex-col gap-1">
                <label htmlFor="cashAmount" className="text-sm font-medium text-text-primary">
                  Cash Amount
                </label>
                <input
                  id="cashAmount"
                  type="text"
                  inputMode="decimal"
                  className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                  aria-invalid={errors.cashAmount ? "true" : "false"}
                  {...register("cashAmount")}
                />
                {errors.cashAmount && (
                  <p role="alert" className="text-sm text-danger">
                    {errors.cashAmount.message}
                  </p>
                )}
              </div>
            )}

            {QUANTITY_PRICE_REQUIRED.has(selectedType) && (
              <div className="flex flex-col gap-1">
                <label htmlFor="fees" className="text-sm font-medium text-text-primary">
                  Fees (optional)
                </label>
                <input
                  id="fees"
                  type="text"
                  inputMode="decimal"
                  className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                  {...register("fees")}
                />
              </div>
            )}

            {serverError && (
              <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
                {serverError}
              </p>
            )}

            <div className="mt-2 flex justify-end gap-2">
              <Button type="button" onClick={onClose} className="bg-transparent text-text-primary">
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Adding…" : "Add Transaction"}
              </Button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
