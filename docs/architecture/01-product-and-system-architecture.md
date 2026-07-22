# INVEST IQ — Architecture Blueprint
## Document 1 of N: Product Architecture, System Architecture, Domain-Driven Design

> Status: DRAFT — pending founder approval
> Scope: This document defines WHAT the system is and the highest-level structure of HOW it is built. Subsequent documents drill into each subsystem.

---

## 1. Product Architecture

### 1.1 Product Definition

INVEST IQ is an AI-assisted investment intelligence and portfolio management platform. It is **not** a licensed broker-dealer and does **not** execute real trades. It provides:

- Market data visualization (real-time/delayed quotes, historical charts)
- Quantitative + ML-driven analysis (technical, fundamental, sentiment, predictive)
- Explainable AI recommendations (Buy/Sell/Hold + confidence + SHAP rationale)
- Portfolio construction, tracking, optimization, and risk scoring
- Paper trading (simulated execution only)
- A conversational AI assistant with tool-calling into the platform's own data

**Legal/compliance framing (binding on architecture):** every prediction, score, or recommendation surfaced by the system must carry (a) a confidence/probability value, (b) an explainability payload, and (c) a persistent "informational, not financial advice" disclaimer at the API contract level (not just UI). This is enforced in the API response envelope (see Document 4, API Design) so no client can accidentally omit it.

### 1.2 Target Users (Personas)

| Persona | Need | Primary Surfaces |
|---|---|---|
| Retail self-directed investor | Research + decision support | Dashboard, Stock Details, Predictions, Screener |
| Active/technical trader | Fast technical signals, patterns | Watchlist, Candlestick patterns, Alerts |
| Long-term/passive investor | Portfolio health, optimization | Portfolio, Risk Analysis, Optimizer, SIP Calculator |
| Learner/paper trader | Practice without capital risk | Paper Trading, AI Assistant |
| Admin/Ops | Platform health, user/content mgmt | Admin Panel |

### 1.3 Product Pillars

1. **Data Integrity** — every number traceable to a source + timestamp.
2. **Explainability over black-box** — no ML output ships without a "why."
3. **Simulation before capital** — paper trading is first-class, not an afterthought.
4. **Composable intelligence** — prediction, sentiment, risk, and optimization are independent services that combine, not a monolith.
5. **Progressive disclosure UI** — dense financial data, disclosed progressively (Bloomberg density, Apple clarity).

### 1.4 Monetization-Ready Structure (future-facing, not built now)

Tiering is designed into the domain model from day one (via `SubscriptionPlan` + `FeatureEntitlement` entities) even though billing integration itself is a later phase:

- **Free** — delayed data, limited watchlist size, basic predictions
- **Pro** — real-time data, full ML suite, portfolio optimizer, AI assistant unlimited
- **Enterprise** — API access, team seats, priority data refresh

---

## 2. System Architecture (C4 Level 1–2)

### 2.1 Architecture Style

**Modular monolith at launch, service-decomposable by design.** This is a deliberate choice, not a shortcut:

- A pure microservices architecture on day one adds operational overhead (service discovery, distributed tracing, network latency, distributed transactions) that a pre-scale startup cannot justify.
- However, every bounded context (see DDD section) is built as an independently deployable module behind clean interfaces, so extraction into a real microservice later is a deployment change, not a rewrite.
- The **ML/AI workloads are the exception** — they are split into a separate Python service (FastAPI + Celery workers) from day one because they have fundamentally different scaling characteristics (CPU/GPU-bound, long-running, batch-friendly) than the request/response API.

### 2.2 C4 Level 1 — System Context

```
                         ┌─────────────────────────┐
                         │        End User          │
                         │  (Browser, responsive/     │
                         │   mobile-first web client) │
                         └────────────┬─────────────┘
                                      │ HTTPS / WSS
                         ┌────────────▼─────────────┐
                         │      INVEST IQ Platform   │
                         │  (Web app + API + AI/ML)  │
                         └──┬───────┬───────┬────────┘
                            │       │       │
              ┌─────────────┘       │       └─────────────┐
              ▼                     ▼                      ▼
   ┌────────────────────┐ ┌──────────────────┐  ┌───────────────────────┐
   │ Market Data Vendors │ │ News/Sentiment    │  │ Auth Providers (OAuth)│
   │ (Polygon/Alpha      │ │ Sources (NewsAPI, │  │ Google/GitHub         │
   │ Vantage/yfinance)   │ │ RSS, Twitter/X)   │  │                       │
   └────────────────────┘ └──────────────────┘  └───────────────────────┘
```

> **REVISION (post-architecture-review):** "PWA" and "(future) Mobile via React Native" were removed from this diagram — they were labeled here with zero corresponding architecture anywhere in the blueprint (no manifest, service worker, or offline strategy). Mobile support for this product is delivered via the responsive web client itself (Document 2 §6.1a), not a separate PWA/native artifact. PWA is recorded as a future ADR candidate (Document 8 §23), not committed scope. See Document 2 §6.7 for the full reasoning.

### 2.3 C4 Level 2 — Containers

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                 │
│         Next.js 15 Web App (SSR/RSC), mobile-first responsive             │
└───────────────────────────┬────────────────────────────────────────────────┘
                             │ HTTPS (REST/JSON) + WSS (real-time)
┌───────────────────────────▼────────────────────────────────────────────────┐
│                          API GATEWAY / BFF LAYER                          │
│      Next.js Route Handlers (BFF) — auth session, request shaping,        │
│      response envelope enforcement, rate-limit headers                    │
└───────────────────────────┬────────────────────────────────────────────────┘
                             │ Internal REST (service-to-service, JWT signed)
                    ┌─────────────────┴──────────────────┐
                    ▼                                     ▼
          ┌───────────────────┐                 ┌──────────────────┐
          │  core-api           │                 │  ai-service        │
          │  (FastAPI)           │                 │  (FastAPI+Celery)  │
          │  Users/Auth/          │                 │  Predictions/      │
          │  Portfolio/Watchlist/  │                 │  Sentiment/Risk/   │
          │  Screener/Alerts/       │                 │  Optimizer/SHAP/   │
          │  Notifications(WS)/      │                 │  Model training    │
          │  Market Data ingestion    │                 │                    │
          └──────┬────────────────┘                 └────────┬───────────┘
                 │                                             │
                 └───────────────┬─────────────────────────────┘
                                 ▼
       ┌─────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
       │   PostgreSQL          │   │  Redis (3 instances:     │   │      MongoDB              │
       │   (relational, ACID)  │   │  cache / broker+streams / │   │  (document store)          │
       │   users, portfolios,  │   │  session — Doc 3 §7.7)     │   │  news, sentiment docs,      │
       │   transactions, bars   │   │                             │   │  ML feature snapshots,       │
       └─────────────────────┘   └────────────────────────┘   │  raw vendor payloads          │
                                                                 └────────────────────────┘
```

> **REVISION (post-architecture-review):** collapsed from 4 backend services to 2 — see Document 3 §7.1 for full rationale (the original 4-way split contradicted this document's own §2.1 modular-monolith reasoning and imposed unjustified local-dev/operational overhead). `market-data-service` and `notification-service` are now modules within `core-api`; `ai-service` remains independently deployable as the one genuinely CPU/GPU-distinct workload. Redis is split into 3 instances by workload (not shown as one box) per Document 3 §7.7's revision, closing a single-point-of-failure/conflicting-persistence-needs gap identified in review.

### 2.4 Why Three Databases (justification, not over-engineering)

| Store | Data | Why this engine |
|---|---|---|
| PostgreSQL | Users, auth, portfolios, holdings, transactions, orders (paper), audit logs | Strong consistency, relational integrity (foreign keys on money-related data are non-negotiable), transactions |
| MongoDB | News articles, sentiment scores, raw market payload snapshots, ML feature vectors, model prediction logs | Schema variability across news sources/vendors, high write volume of semi-structured documents, no need for joins |
| Redis | Session cache, live quote cache, rate-limit counters, Celery broker/result backend, WebSocket pub/sub fan-out | Sub-millisecond reads for hot data, native pub/sub for real-time fan-out to WS connections |

This is deliberately **polyglot persistence**, justified per-workload, not "using every database because we can."

### 2.5 Real-Time Data Flow (high level)

```
Vendor API/WebSocket ──▶ core-api: Market Data module ──▶ redis-cache (latest tick cache)
                                                    │
                                                    ├──▶ Redis Pub/Sub channel "quotes:{symbol}"
                                                    │
                                                    └──▶ core-api: Notification module subscribes ──▶ WSS ──▶ Client
```
Clients never talk to vendor APIs directly (API key security + normalization + rate-limit pooling across all users). Both modules run within the `core-api` deployable (Document 3 §7.1 revision) but communicate only through Redis Pub/Sub, not direct in-process calls — preserving the same decoupling a separate-service boundary would have provided, without the deployment overhead.

---

## 3. Domain-Driven Design

### 3.1 Bounded Contexts

| Bounded Context | Responsibility | Core Aggregates |
|---|---|---|
| **Identity & Access** | Auth, users, roles, sessions, API keys | `User`, `Role`, `Session`, `ApiKey` |
| **Market Data** | Symbols, quotes, historical bars, corporate actions | `Instrument`, `Quote`, `OHLCVBar`, `CorporateAction` |
| **Portfolio** | Holdings, transactions, paper orders, performance | `Portfolio`, `Holding`, `Transaction`, `PaperOrder` |
| **Watchlist** | User-curated symbol lists + alerts | `Watchlist`, `Alert` |
| **Prediction (ML)** | Price forecasts, model runs, confidence | `PredictionRun`, `ModelVersion`, `Forecast` |
| **Sentiment** | News ingestion, NLP scoring | `NewsArticle`, `SentimentScore` |
| **Risk** | Portfolio risk scoring, VaR, volatility | `RiskProfile`, `RiskAssessment` |
| **Optimization** | Portfolio allocation suggestions | `OptimizationRequest`, `AllocationSuggestion` |
| **Recommendation** | Buy/Sell/Hold synthesis across signals | `Recommendation`, `ExplainabilityPayload` |
| **Screener** | Multi-factor stock filtering | `ScreenerQuery`, `ScreenerResult` |
| **Notification** | Alerts, system messages, delivery | `Notification`, `NotificationPreference` |
| **Billing (future-ready)** | Plans, entitlements | `SubscriptionPlan`, `FeatureEntitlement` |
| **AI Assistant** | Conversational tool-calling layer | `ConversationSession`, `AssistantMessage`, `ToolInvocation` |

### 3.2 Context Map (relationships)

```
Identity & Access ──(shared kernel: UserId)──▶ every other context

Market Data ──(published events: QuoteUpdated, BarClosed)──▶ Prediction, Watchlist, Portfolio

Sentiment ──(published events: SentimentScored)──▶ Recommendation

Prediction ──(published events: ForecastGenerated)──▶ Recommendation

Risk ──(consumes: Portfolio snapshot via ACL)──▶ Optimization

Recommendation ──(consumer of: Prediction + Sentiment + Risk)──▶ presented in Stock Details, AI Assistant

Portfolio ──(consumes: Market Data quotes via ACL — Anti-Corruption Layer)──▶ live valuation

AI Assistant ──(orchestrates via tool calls into)──▶ Portfolio, Market Data, Recommendation, Risk
```

Key DDD pattern used: **Anti-Corruption Layer (ACL)** between Market Data (external vendor shapes) and every internal context. Vendor payloads are never passed through the system raw — they are mapped to internal `Instrument`/`OHLCVBar` value objects at the ingestion boundary. This means swapping Polygon for Alpha Vantage later touches one adapter, not the whole codebase.

### 3.3 Ubiquitous Language (core terms, fixed across all code/docs)

| Term | Definition |
|---|---|
| Instrument | Any tradable security (stock, ETF, index) identified by ticker + exchange |
| Bar | OHLCV data point for one time interval |
| Holding | A position within a Portfolio (symbol + quantity + cost basis) |
| PaperOrder | A simulated buy/sell order, never touches real markets |
| Forecast | A single model's predicted price/direction for an Instrument over a horizon |
| Recommendation | The synthesized Buy/Sell/Hold verdict combining Forecast + Sentiment + Risk |
| Confidence | 0–1 probability-like score attached to every Forecast/Recommendation |
| ExplainabilityPayload | SHAP/LIME feature-attribution data justifying a Recommendation |
| RiskProfile | User's declared/derived risk tolerance (Conservative/Moderate/Aggressive) |
| RiskAssessment | Computed risk metrics for a specific Portfolio (volatility, VaR, Sharpe, beta) |

### 3.4 Aggregate Design Rules (enforced in code review / architecture)

1. **Portfolio aggregate owns Holdings.** No code outside the Portfolio module mutates a Holding directly — all mutations go through `Portfolio.applyTransaction()` domain logic to guarantee cost-basis and quantity invariants.
2. **Money is never a float.** All monetary values use `Decimal` (Python `Decimal`, TS using a fixed-point decimal library, e.g. `decimal.js`), never IEEE floats — non-negotiable for financial correctness.
3. **PredictionRun is immutable once created.** Forecasts are append-only, versioned by `ModelVersion` — you never overwrite a past prediction (required for backtesting model accuracy over time).
4. **Cross-context communication happens via events or ACL, never direct DB access across contexts.** Even inside the monolith, Portfolio module never queries Market Data's tables directly — it calls Market Data's internal service interface. This is what makes future extraction to microservices mechanical rather than a rewrite.

---

*End of Document 1. Continuing in Document 2: Clean Architecture layering, Folder Structure, and Frontend Architecture.*
