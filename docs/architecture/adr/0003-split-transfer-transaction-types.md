# ADR-0003: Extend `transactions.type` to Include `split` and `transfer`

**Status:** Accepted (founder ratification, 2026-07-22)
**Date:** 2026-07-22
**Supersedes/amends:** Document 3 (`03-backend-architecture-database-design.md`) §8.1 — the `transactions` table's `type` CHECK constraint, currently `IN ('buy','sell','dividend','deposit','withdrawal')`.

## Context

Phase 3's explicit requirements (founder instruction) list transaction types as: Buy, Sell, Dividend, **Split**, **Transfer**, Cash Deposit, Cash Withdrawal. The frozen architecture's `transactions` schema (Document 3 §8.1) only permits `('buy','sell','dividend','deposit','withdrawal')` — `split` and `transfer` are absent.

This is the same category of gap as ADR-0002 (login history): an explicit new requirement that the frozen schema does not yet accommodate. Per the founder's standing rule ("if simplification or extension becomes necessary, create an ADR first and wait for approval"), this ADR proposes the smallest correct additive extension.

Two design questions had to be resolved to specify this correctly, not just "add two enum values":

1. **Split is not a cash-flow transaction at all** — it doesn't change cost basis or quantity's dollar value, it changes quantity and per-share price proportionally (e.g., a 2:1 split doubles quantity and halves average cost, net position value unchanged). This is fundamentally different from buy/sell/dividend/deposit/withdrawal, all of which do represent a real cash flow or position-value change.
2. **Transfer is ambiguous** — it could mean (a) a security transferred *into* this portfolio from an external account (no cost-basis-affecting cash flow, just an inbound position), (b) a security transferred *out* to an external account, or (c) a transfer *between two of the user's own portfolios* (Document 3 §3's multi-portfolio-per-user model, explicitly requested in Phase 3, makes this a real scenario). These have different implications for realized/unrealized gain calculation and must be distinguishable in the data.

## Decision

Extend the `transactions` table (additive only — no existing column removed or retyped):

```sql
ALTER TABLE transactions
    DROP CONSTRAINT IF EXISTS transactions_type_check;
ALTER TABLE transactions
    ADD CONSTRAINT transactions_type_check
    CHECK (type IN ('buy','sell','dividend','split','transfer_in','transfer_out','deposit','withdrawal'));

ALTER TABLE transactions ADD COLUMN split_ratio NUMERIC(20,8);
    -- e.g. 2.0 for a 2:1 split, 0.5 for a 1:2 reverse split. NULL for all
    -- other transaction types. Quantity/average_cost adjustment is computed
    -- from this ratio (Holding.apply_split()), not stored redundantly.

ALTER TABLE transactions ADD COLUMN related_portfolio_id UUID REFERENCES portfolios(id);
    -- Populated only for transfer_in/transfer_out where the counterparty is
    -- ANOTHER of the user's own portfolios (Document 3 §3's multi-portfolio
    -- model) — links the two legs of an internal transfer for audit/display
    -- purposes. NULL for transfers to/from external accounts (the common
    -- case: "I transferred shares in from my broker") and for all non-transfer
    -- transaction types.
```

- **`split`** is resolved to a *single* transaction type (not `split_in`/`split_out`) since it never involves a counterparty — it is always a unilateral position adjustment. `split_ratio` carries the adjustment factor.
- **`transfer_in`/`transfer_out`** (two distinct types, not one ambiguous `transfer`) because they have opposite effects on the receiving vs. sending side and must be distinguishable in a `WHERE type = ...` filter without inspecting sign/quantity. This directly resolves ambiguity (b) above.
- **`related_portfolio_id`** resolves ambiguity (c): an internal transfer between the user's own portfolios creates two transaction rows (one `transfer_out` on the source portfolio, one `transfer_in` on the destination), each referencing the other's portfolio via this column. An external transfer (the more common real-world case) simply leaves this `NULL`.
- **Realized/unrealized gain treatment (application-layer rule, not a schema concern, but stated here for completeness since it's what this ADR's design choices exist to support):** `transfer_in` establishes a new cost basis at the transferred-in price/quantity (as if a purchase, but explicitly flagged `is_transfer=true` in the calculation service so it's distinguishable from an actual cash-outflow buy in the Total Investment calculation); `transfer_out` reduces the holding's quantity without generating a realized gain/loss event (unlike a `sell`, which does) — this matches standard brokerage/tax treatment of security transfers.

## Consequences

- **Easier:** the transaction model now correctly represents every transaction type the founder explicitly requested, with split and transfer's genuinely different semantics kept distinguishable rather than forced into the existing 5 types.
- **Given up (for now):** no support for partial/fractional-share splits with non-integer ratios beyond what `NUMERIC(20,8)` naturally allows (this is not a real limitation — decimal ratios like 1.5 for a 3:2 split are fully supported); no support for a *taxable* transfer (a transfer that itself triggers a realized gain, e.g. certain in-kind distributions) — explicitly out of scope, not requested.
- **Reversible:** yes — both the CHECK constraint change and the two new nullable columns are purely additive; downgrading is a `DROP COLUMN`/constraint revert with no data loss for the pre-existing 5 transaction types.
- **No existing frozen-architecture table or column is modified or removed.**

## Alternatives Considered

- **Model `split` as a `sell` + `buy` pair (synthetic transactions).** Rejected: this would fabricate a cost-basis-affecting cash flow that never happened, corrupting the Total Investment and Realized Gain calculations Phase 3 explicitly requires.
- **Single `transfer` type with a signed quantity to indicate direction.** Rejected: signed quantities are a fragile convention (easy to introduce a sign-flip bug in the calculation service) compared to two explicit, self-describing type values — and Document 3 §3.4's own aggregate design rules favor explicitness over implicit convention.
- **Skip split/transfer for Phase 3, implement only the 5 already-frozen types.** Rejected: explicitly requested by the founder for this phase; deferring would contradict "do not scaffold, actually implement" from Phase 2's own standing instruction, which continues to apply.
