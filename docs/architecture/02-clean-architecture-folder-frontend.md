# INVEST IQ — Architecture Blueprint
## Document 2 of N: Clean Architecture, Folder Structure, Frontend Architecture

> Status: DRAFT — pending founder approval

---

## 4. Clean Architecture Layering

Applied identically in concept across both the Next.js frontend and the FastAPI backend services, adapted to each ecosystem's idioms.

### 4.1 The Four Layers (Backend — FastAPI services)

```
┌─────────────────────────────────────────────────────────────┐
│  1. PRESENTATION (API)                                        │
│     FastAPI routers, request/response DTOs (Pydantic),        │
│     dependency-injected auth guards, exception handlers        │
├─────────────────────────────────────────────────────────────┤
│  2. APPLICATION (Use Cases)                                    │
│     Use-case classes (e.g. CreatePortfolioUseCase,              │
│     GenerateForecastUseCase), orchestrates domain + repos,      │
│     no framework imports here                                   │
├─────────────────────────────────────────────────────────────┤
│  3. DOMAIN (Enterprise Business Rules)                          │
│     Entities, Value Objects, Domain Services, Domain Events,    │
│     Repository INTERFACES (protocols) — zero external deps      │
├─────────────────────────────────────────────────────────────┤
│  4. INFRASTRUCTURE                                              │
│     Repository IMPLEMENTATIONS (SQLAlchemy, Mongo, Redis),       │
│     vendor API adapters, Celery task definitions, ORM models    │
└─────────────────────────────────────────────────────────────┘
```

**Dependency rule (strict):** Presentation → Application → Domain ← Infrastructure. Domain has zero knowledge of Infrastructure. Infrastructure implements Domain-defined interfaces (Dependency Inversion Principle). This is what makes the domain layer testable with zero mocks-of-mocks and swappable persistence.

Example dependency direction for the Prediction context:

```python
# domain/prediction/repositories.py  (interface — lives in Domain)
class ForecastRepository(Protocol):
    async def save(self, forecast: Forecast) -> None: ...
    async def get_latest(self, instrument_id: InstrumentId) -> Forecast | None: ...

# infrastructure/prediction/mongo_forecast_repository.py (implementation)
class MongoForecastRepository(ForecastRepository):
    async def save(self, forecast: Forecast) -> None:
        await self._collection.insert_one(ForecastDocument.from_domain(forecast).dict())
    ...

# application/prediction/generate_forecast_use_case.py
class GenerateForecastUseCase:
    def __init__(self, repo: ForecastRepository, model_client: ModelInferenceClient):
        self._repo = repo          # depends on interface, not Mongo
        self._model_client = model_client
    async def execute(self, cmd: GenerateForecastCommand) -> Forecast:
        ...
```

### 4.2 The Four Layers (Frontend — Next.js)

```
┌─────────────────────────────────────────────────────────────┐
│  1. PRESENTATION                                               │
│     app/ routes, page components, layout components,           │
│     shadcn/ui-based dumb components                             │
├─────────────────────────────────────────────────────────────┤
│  2. APPLICATION                                                 │
│     Feature hooks (useCreateWatchlistItem), React Query          │
│     mutations/queries, Redux slices (for cross-cutting client    │
│     state only — auth session, UI prefs, NOT server data)         │
├─────────────────────────────────────────────────────────────┤
│  3. DOMAIN (client-side mirror, thin)                           │
│     TypeScript types/interfaces mirroring backend domain          │
│     entities, Zod schemas as the single source of validation      │
│     truth (shared between form validation and API contracts)      │
├─────────────────────────────────────────────────────────────┤
│  4. INFRASTRUCTURE                                              │
│     API client (typed fetch wrapper), WebSocket client,           │
│     localStorage/IndexedDB adapters, analytics adapters           │
└─────────────────────────────────────────────────────────────┘
```

**Critical rule:** React Query owns all server state. Redux Toolkit owns only genuinely global client-only state (auth session shape, theme, sidebar collapsed, active AI assistant panel). Server data is never duplicated into Redux — this avoids the classic "two sources of truth out of sync" bug class entirely.

---

## 5. Folder Structure

### 5.1 Monorepo Root

```
investiq/
├── apps/
│   ├── web/                      # Next.js 15 app (frontend)
│   ├── core-api/                 # FastAPI — users/auth/portfolio/watchlist/screener/
│   │                              #   alerts/notifications(WS)/market-data (Document 3
│   │                              #   §7.1 revision: collapsed from 3 separate services
│   │                              #   into modules here — see that section for rationale)
│   └── ai-service/               # FastAPI + Celery — prediction/sentiment/risk/optimizer/SHAP
│                                   # (kept independently deployable — genuinely distinct
│                                   #   CPU/GPU-bound scaling profile, per Document 1 §2.1)
├── packages/
│   ├── ui/                       # Shared React component library (shadcn-based, exported)
│   ├── config/                   # Shared eslint/tsconfig/tailwind config
│   ├── types/                    # Shared TS types generated from OpenAPI schemas
│   └── validation/                # Shared Zod schemas
├── libs/                          # Python shared libs (installed as editable packages)
│   ├── domain_common/             # Shared value objects (Money, Percentage, Ticker) +
│   │                                #   features/registry.py (shared feature definitions,
│   │                                #   Document 4 §10.2 revision — used by both
│   │                                #   ml/training/ and ai-service to prevent train/serve skew)
│   ├── auth_common/               # JWT verification shared across Python services
│   └── observability/             # Shared logging/tracing setup
├── infra/
│   ├── docker/                    # Dockerfiles per service
│   ├── docker-compose.yml         # Local dev orchestration
│   ├── docker-compose.prod.yml
│   ├── k8s/                       # (Phase 9+) Kubernetes manifests, kept ready not required at launch
│   └── nginx/                     # Reverse proxy config for local/prod
├── ml/
│   ├── notebooks/                 # Exploratory research (not shipped)
│   ├── training/                  # Training pipelines per model family
│   ├── models/                    # Versioned model artifacts (git-lfs or object storage pointer)
│   └── evaluation/                # Backtesting + accuracy tracking scripts
├── docs/
│   └── architecture/              # This blueprint, ADRs, diagrams
├── .github/workflows/             # CI/CD pipelines
├── scripts/                       # Dev bootstrap, migration runners
└── package.json                   # Root workspace (pnpm workspaces / turborepo)
```

### 5.2 `apps/web` (Next.js) — Feature-Based Structure

```
apps/web/
├── app/                                    # Next.js App Router (routing only, thin)
│   ├── (marketing)/
│   │   ├── page.tsx                        # Landing page
│   │   ├── pricing/page.tsx
│   │   └── layout.tsx
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   ├── register/page.tsx
│   │   └── layout.tsx
│   ├── (app)/                              # Authenticated app shell
│   │   ├── dashboard/page.tsx
│   │   ├── portfolio/[portfolioId]/page.tsx
│   │   ├── watchlist/page.tsx
│   │   ├── stocks/[symbol]/page.tsx
│   │   ├── predictions/page.tsx
│   │   ├── news/page.tsx
│   │   ├── sentiment/page.tsx
│   │   ├── market-overview/page.tsx
│   │   ├── risk-analysis/page.tsx
│   │   ├── optimizer/page.tsx
│   │   ├── paper-trading/page.tsx
│   │   ├── assistant/page.tsx
│   │   ├── settings/page.tsx
│   │   ├── notifications/page.tsx
│   │   ├── profile/page.tsx
│   │   └── layout.tsx                      # Sidebar + topbar shell
│   ├── admin/
│   │   └── page.tsx
│   ├── api/                                # BFF route handlers (thin proxies + session)
│   │   └── [...proxied routes]/route.ts
│   └── layout.tsx                          # Root layout (fonts, providers)
│
├── features/                               # THE CORE — feature-based modules
│   ├── auth/
│   │   ├── components/                     # LoginForm, RegisterForm, OAuthButtons
│   │   ├── hooks/                          # useLogin, useSession
│   │   ├── api/                            # authApi.ts (typed client calls)
│   │   ├── schemas/                        # loginSchema.ts (Zod)
│   │   └── types.ts
│   ├── portfolio/
│   │   ├── components/                     # HoldingsTable, PortfolioSummaryCard, AllocationDonut
│   │   ├── hooks/                          # usePortfolio, useAddHolding, useTransactions
│   │   ├── api/
│   │   ├── schemas/
│   │   └── types.ts
│   ├── watchlist/
│   ├── stock-details/
│   │   ├── components/                     # PriceChart, KeyStats, CandlestickPatternBadge
│   ├── predictions/
│   │   ├── components/                     # ForecastCard, ConfidenceGauge, ShapExplainer
│   ├── sentiment/
│   ├── market-overview/
│   │   ├── components/                     # HeatmapGrid, IndexTicker
│   ├── risk-analysis/
│   ├── optimizer/
│   ├── paper-trading/
│   ├── ai-assistant/
│   │   ├── components/                     # ChatWindow, MessageBubble, ToolCallCard
│   │   ├── hooks/                          # useAssistantStream (WS/SSE)
│   ├── notifications/
│   ├── admin/
│   └── screener/
│
├── components/                             # TRULY generic, feature-agnostic UI only
│   ├── ui/                                 # shadcn primitives (button, dialog, etc.)
│   ├── charts/                             # Generic chart wrappers (TradingView, Recharts)
│   ├── layout/                             # Sidebar, Topbar, PageContainer
│   ├── animations/                         # MagneticButton, GlowCard, ParallaxWrapper
│   └── three/                              # R3F scenes (AIBrain, NeuralNetworkBg, ParticleField)
│
├── hooks/                                  # Cross-feature generic hooks (useDebounce, useMediaQuery)
├── lib/
│   ├── api-client.ts                       # Typed fetch wrapper, interceptors, error mapping
│   ├── websocket-client.ts
│   ├── query-client.ts                     # React Query client + default options
│   └── utils.ts
├── store/
│   ├── slices/                             # authSlice, uiSlice, assistantPanelSlice
│   └── store.ts
├── styles/
│   └── globals.css                         # Tailwind base + design tokens
├── types/                                  # Global ambient types
├── middleware.ts                           # Next.js middleware — route protection, i18n
├── next.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

**Rule enforced by this structure:** a `features/portfolio` file must never import from `features/watchlist` directly. Cross-feature composition happens only at the `app/` route level or via explicitly exported public hooks (`features/portfolio/index.ts` barrel), preventing the "spaghetti feature coupling" failure mode common in feature-based frontends.

### 5.3 `apps/core-api` (FastAPI) — Clean Architecture per Bounded Context

```
apps/core-api/
├── src/
│   ├── main.py                             # FastAPI app factory, router registration
│   ├── config.py                           # Pydantic Settings (env-driven)
│   │
│   ├── presentation/
│   │   ├── routers/
│   │   │   ├── auth_router.py
│   │   │   ├── portfolio_router.py
│   │   │   ├── watchlist_router.py
│   │   │   └── screener_router.py
│   │   ├── dependencies/                   # get_current_user, require_role()
│   │   ├── dto/                            # Pydantic request/response schemas
│   │   └── exception_handlers.py
│   │
│   ├── application/
│   │   ├── auth/
│   │   │   ├── commands/                   # RegisterUserCommand + handler
│   │   │   └── queries/
│   │   ├── portfolio/
│   │   │   ├── commands/                   # CreatePortfolioUseCase, AddHoldingUseCase
│   │   │   └── queries/                    # GetPortfolioSummaryQuery
│   │   ├── watchlist/
│   │   └── screener/
│   │
│   ├── domain/
│   │   ├── auth/
│   │   │   ├── entities.py                 # User, Role
│   │   │   ├── value_objects.py            # Email, HashedPassword
│   │   │   └── repositories.py             # UserRepository (Protocol)
│   │   ├── portfolio/
│   │   │   ├── entities.py                 # Portfolio, Holding, Transaction (aggregate root logic)
│   │   │   ├── value_objects.py            # Money, Quantity, CostBasis
│   │   │   ├── events.py                   # HoldingAdded, TransactionRecorded
│   │   │   ├── exceptions.py               # InsufficientHoldingQuantity
│   │   │   └── repositories.py             # PortfolioRepository (Protocol)
│   │   ├── watchlist/
│   │   └── shared_kernel/                  # Ticker, UserId, Money (used across contexts)
│   │
│   └── infrastructure/
│       ├── persistence/
│       │   ├── postgres/
│       │   │   ├── models.py               # SQLAlchemy ORM models
│       │   │   ├── repositories/           # SqlAlchemyPortfolioRepository etc.
│       │   │   └── session.py
│       │   └── redis/
│       │       └── cache_repository.py     # note: separate repos/clients per Redis
│       │                                      instance role (cache/broker/session),
│       │                                      per Document 3 §7.7's 3-way split
│       ├── external/
│       │   ├── market_data_provider_clients/  # Polygon/AlphaVantage/yfinance adapters
│       │   │                                    (Document 5 §11.1) — internal to
│       │   │                                    core-api now, not a separate service
│       │   ├── ai_service_client.py            # real HTTP client to ai-service
│       │   └── mock_ai_service_client.py       # local-dev fixture-based implementation
│       │                                         of the same interface (Document 3 §7.1)
│       └── security/
│           ├── jwt_provider.py
│           └── password_hasher.py          # bcrypt wrapper
│
├── tests/
│   ├── unit/                               # domain + application, no I/O, no DB
│   ├── integration/                        # real Postgres via testcontainers
│   └── e2e/                                # full API via httpx AsyncClient
├── alembic/                                 # DB migrations
├── pyproject.toml
└── Dockerfile
```

Same pattern repeats structurally for `ai-service` — it owns its own bounded contexts' (Prediction, Sentiment, Risk, Optimization) domain/application/infrastructure layers, no cross-service ORM model sharing with `core-api`. (Originally this note referenced `market-data-service` and `notification-service` as additional separate services; both are now modules within `core-api` itself per Document 3 §7.1's post-review revision, each still following the same domain/application/infrastructure layering internally — the module boundary is preserved, only the deployment boundary changed.)

---

## 6. Frontend Architecture (Detailed)

### 6.1 Rendering Strategy Per Route

| Route type | Strategy | Reason |
|---|---|---|
| Landing page | Static Generation (SSG) + ISR (revalidate 1hr) | SEO, marketing, rarely changes |
| Auth pages | Client-rendered (CSR) | Form-heavy, no SEO need |
| Dashboard/Portfolio/Watchlist | Server Components for initial data + Client Components for live updates | Fast first paint, then WS takes over |
| Stock Details | Hybrid — RSC for static company info (SSR), Client Component for live price/chart | Chart needs client-side interactivity + WS |
| Admin Panel | CSR, behind auth wall, no SEO concern | Simpler data-table heavy CRUD |

### 6.1a Responsive Strategy (missing entirely from the original draft — added per architecture review)

The original blueprint had no stated breakpoint scale, no minimum supported viewport, and no mobile adaptation pattern for dense data tables anywhere — a critical gap given the product's own stated personas (Document 1 §1.2, retail/active traders) access dense financial data on mobile browsers with no native app until a "future" phase. Specified now, mobile-first:

**Breakpoint scale** (Tailwind defaults, adopted rather than inventing custom values — standard, well-understood, sufficient for this product's needs):

| Breakpoint | Min-width | Primary use |
|---|---|---|
| (base, no prefix) | 0px | Mobile phones — this is the DEFAULT design target, not a fallback; components are designed here first, then enhanced upward |
| `sm` | 640px | Large phones / small tablets portrait |
| `md` | 768px | Tablets |
| `lg` | 1024px | Small laptops — sidebar navigation becomes viable |
| `xl` | 1280px | Desktops — full dashboard density |
| `2xl` | 1536px | Large desktops / trading-focused multi-panel layouts |

**Minimum supported viewport: 360px width** (covers the vast majority of active Android devices; iOS Safari's smallest current viewport is wider than this). Below 360px is explicitly unsupported — horizontal scroll is acceptable there, not a bug to chase.

**Dense data table adaptation (holdings, screener results, watchlist) — the specific gap flagged in review:** the `DataTable` composite component (§6.3) takes a required `mobileRenderMode: 'card' | 'scroll'` prop:
- `'card'` (default for Holdings, Watchlist, Screener results): below `md`, each row renders as a stacked card showing the 2-3 most important fields prominently (symbol, price, change%) with the rest revealed on tap/expand — not a shrunken version of the full desktop table.
- `'scroll'` (used for read-only comparison/history tables where card-per-row would lose useful side-by-side comparison, e.g. Forecast History): below `md`, the table becomes horizontally scrollable with the first column (symbol/date) sticky, so context is never lost while scrolling.
- Every `DataTable` instance in `features/*/components/` must declare this prop explicitly (no silent default reliance) and include a corresponding Storybook viewport story (Document 8 §23) demonstrating the mobile rendering.

**Screener filter panel on mobile**: the multi-factor filter UI (a persistent sidebar on `lg`+) becomes a slide-over `Sheet` (Radix) below `md`, triggered by a "Filters" button — `features/screener/components/FilterPanel.tsx` implements both layouts behind the same breakpoint check, sharing the same underlying `nuqs` URL-state logic (§6.2) so filtered views remain bookmarkable/shareable regardless of viewport.

**Touch targets**: all interactive elements (row actions, checkboxes, chart legend toggles) maintain a minimum 44×44px touch target below `md`, achieved via padding rather than shrinking visual icon size (WCAG 2.5.5 guidance).

### 6.2 State Management Decision Matrix

| State type | Tool | Example |
|---|---|---|
| Server-owned data (fetched from API) | React Query | Portfolio holdings, quotes, predictions |
| Global client-only UI state | Redux Toolkit | Sidebar collapsed, theme mode (light/dark/system — see §6.3a), assistant panel open/closed |
| Local component state | `useState`/`useReducer` | Form field focus, modal open |
| Form state + validation | React Hook Form + Zod | All forms platform-wide |
| Real-time streaming state | React Query + WS bridge (custom `useLiveQuote` hook that patches the query cache on message) | Live price ticks |
| URL state | `useSearchParams` / nuqs | Screener filters, pagination, sort |

**Why not put live quotes in Redux:** live quotes are server-owned, high-frequency data. Piping WS messages into React Query's cache (`queryClient.setQueryData`) means every component reading that query via `useQuery` re-renders correctly with zero extra plumbing, and it participates in the same stale-time/gc-time lifecycle as REST-fetched data. Redux would require manual subscription management duplicating what React Query already does.

### 6.3 Design System Architecture

Built as `packages/ui` — a standalone, versioned internal package so `apps/web` consumes it like any other dependency, and it's portable if a future marketing site or mobile-web variant is added.

```
packages/ui/
├── src/
│   ├── primitives/           # Wrapping shadcn/Radix — Button, Input, Dialog, Select, Tooltip
│   ├── composite/             # Card, StatCard, DataTable, Badge, ConfidenceGauge
│   ├── charts/                 # PriceChart (TradingView lightweight-charts wrapper), Sparkline, Heatmap
│   ├── motion/                 # AnimatedCounter, MagneticButton, GlowCard, FadeInWhenVisible
│   ├── three/                  # AIBrainScene, NeuralNetworkBackdrop, ParticleField (R3F)
│   ├── tokens/                 # design-tokens.ts — colors, spacing, radii, shadows, typography scale, viewport
│   └── index.ts                # public exports
```

> **REVISION (post-architecture-review):** the original token file defined colors as flat hardcoded hex values with `dark: '#111827'` sitting alongside brand colors as if it were just another color — not a theme mode. There was no dark-mode theming mechanism, no persisted preference, and no `prefers-color-scheme` detection anywhere in the blueprint, despite dark mode being implied by the palette and by Document 8 Phase 1's "dark/light considerations" note. **Fix: semantic CSS-variable tokens with explicit light/dark pairs, from day one**, so this isn't retrofitted after primitives are already built against hardcoded hex values (expensive rework avoided by fixing it before Phase 1 implementation begins).

```ts
// packages/ui/src/tokens/colors.ts
// Semantic tokens — components reference --color-* variables, never raw brand hex values.
export const brandPalette = {
  purple: '#6C3BFF',
  white: '#FFFFFF',
  slate50: '#F8FAFC',
  slate900: '#111827',      // renamed from the ambiguous `dark` — this is a palette
                              // value FEEDING the dark theme, not the theme switch itself
  emerald: '#10B981',
  red: '#EF4444',
  amber: '#F59E0B',
} as const;

// Semantic pairs, toggled via next-themes' `dark:` class strategy
export const semanticTokens = {
  light: {
    '--color-background': brandPalette.slate50,
    '--color-surface': brandPalette.white,
    '--color-text-primary': brandPalette.slate900,
    '--color-primary': brandPalette.purple,
  },
  dark: {
    '--color-background': brandPalette.slate900,
    '--color-surface': '#1A2233',                // distinct from background for card elevation contrast
    '--color-text-primary': brandPalette.white,
    '--color-primary': '#8B5FFF',                 // lightened purple for sufficient contrast on dark surface
  },
} as const;
```

### 6.3a Theming Architecture (missing entirely from the original draft — added per architecture review)

- **Mechanism**: `next-themes` + Tailwind's `dark:` class strategy (applies a `class="dark"` on `<html>`, CSS variables above swap accordingly) — chosen over a `data-theme` attribute purely for `next-themes`' out-of-the-box Next.js App Router support.
- **Detection & persistence**: defaults to `prefers-color-scheme` (system) on first visit; explicit user choice (light/dark/system) persisted to `localStorage` and mirrored into the Redux `uiSlice` (§6.2) alongside "sidebar collapsed" so other client-state-dependent UI (e.g., chart theme variants for TradingView lightweight-charts, which needs its own theme config passed explicitly since it doesn't inherit CSS variables) can react to it.
- **Component requirement**: every `packages/ui` component is designed and Storybook-documented (Document 8 §23) against both themes from creation — dark mode is not a follow-up pass.

### 6.4 SEO Architecture (missing entirely from the original draft — added per architecture review)

The original blueprint's entire SEO specification was one line ("SSG + ISR for the landing page — SEO, marketing"). Given the freemium growth model (Document 1 §1.4) implicitly depends on organic acquisition, and stock-details pages are inherently indexable/shareable content, this is specified concretely:

- **Per-route metadata**: `generateMetadata()` (Next.js App Router) on every public route, with dynamic Open Graph + Twitter Card images generated via `@vercel/og` for marketing pages and public stock-details pages (a shareable "AAPL — $231.42, AI Forecast: Hold (72% confidence)" preview card, generated at request time from live data).
- **Structured data**: a shared `<StructuredData>` component in `packages/ui` injects JSON-LD (schema.org `Organization`, `FAQPage` on the landing page's FAQ section, `BreadcrumbList` on nested routes). Stock-details pages do NOT use `FinancialProduct`/investment-advice-adjacent schema types, deliberately — this would risk implying the structured data itself is a financial product listing, which conflicts with the platform's own "not financial advice" posture (Document 1 §1.1); plain `Article`/`WebPage` schema is used instead.
- **Crawlability**: `app/sitemap.ts` auto-generates `sitemap.xml` covering marketing pages and any unauthenticated public stock-details routes; `app/robots.ts` disallows `/app/*`, `/admin/*`, `/api/*` (authenticated/private surfaces are never intended to be indexed).
- **Canonical URLs**: enforced on paginated/filtered routes (screener, news) via a `<link rel="canonical">` pointing to the unfiltered base URL where appropriate, preventing duplicate-content penalties from query-string variants.
- **Lighthouse SEO gate** (Document 6 §16.3) validates the technical baseline (viewport meta, crawlable links) this architecture produces — it is a check on the implementation above, not a substitute for it.

### 6.5 Accessibility Standards — Component-Level Design Requirements (missing entirely from the original draft — added per architecture review)

The original blueprint specified accessibility only as a *testing* gate (axe-core + eslint-plugin-jsx-a11y, Document 6 §16.3), with zero corresponding *design* requirements in this section — testing for WCAG AA compliance against components never designed with accessibility primitives fails repeatedly and late, since axe-core catches missing labels but not "the live price ticker has no ARIA live region, so screen reader users get silent, unannounced financial data changes." Fixed here with concrete, testable component-level rules:

- **Live-updating data (the highest-churn UI surface in the product)**: any component consuming `useLiveQuote`/WS-patched React Query data wraps the changing value in `aria-live="polite"`. High-frequency tickers do NOT announce every tick (would spam screen reader output) — a manual-announce threshold applies: announce only on a >1% price change or at most every 30 seconds, whichever comes first.
- **Chart accessibility**: `PriceChart`, `ConfidenceGauge`, `ShapExplainer`, and `HeatmapGrid` (all canvas/SVG/WebGL-based, not natively accessible) each expose either a keyboard-navigable tabular data fallback (visually hidden but screen-reader-reachable, toggleable via a visible "View as table" control) or, at minimum, an `aria-describedby` textual summary of the chart's key takeaway (e.g., "AAPL forecast: $238 in 7 days, 72% confidence, driven primarily by positive earnings sentiment").
- **Focus management**: all Radix `Dialog` usages (the primitive already ships this, but it is stated here as a non-negotiable so no custom modal bypasses it) trap focus while open and return focus to the triggering element on close.
- **Keyboard navigation**: every interactive control reachable via Tab in a logical order; a skip-to-content link is present in the root layout (`app/layout.tsx`).
- **Reduced motion — platform-wide, not just 3D** (see also §6.6 revision below): a shared `useReducedMotion()` wrapper hook (Framer Motion ships the underlying primitive) gates every transform-based animation, scroll-linked parallax, and auto-playing scroll reveal, not only the 3D scenes the original draft scoped this to.
- **Enforcement**: axe-core + jsx-a11y (Document 6 §16.3) now enforce these stated rules rather than being the only accessibility specification that exists — the design requirements above are the spec; the tools are the regression guard.

### 6.6 Animation Architecture

| Layer | Tool | Use case |
|---|---|---|
| Micro-interactions (hover, tap, focus) | Framer Motion `motion.div` + `whileHover`/`whileTap` | Buttons, cards |
| Page/route transitions | Framer Motion `AnimatePresence` | Route change fades |
| Scroll-triggered reveals | Framer Motion `useInView` / GSAP ScrollTrigger | Landing page sections |
| Complex timeline sequences | GSAP | Hero section multi-element choreography |
| 3D scenes | React Three Fiber + drei helpers | AI Brain, neural network background |
| Pre-built 3D/interactive scenes | Spline (embedded via `@splinetool/react-spline`) | Hero centerpiece if design team produces Spline scene instead of hand-coded R3F |
| Chart animations | Framer Motion + chart library's native transition config | Animated counters on stat cards, chart line draw-in |

**Performance governance (binding rule, not a suggestion):**
- All R3F/Three.js scenes must be dynamically imported (`next/dynamic`, `ssr: false`) — never in the main bundle.
- 3D scenes must detect `prefers-reduced-motion` and low-end devices (via a simple heuristic: `navigator.hardwareConcurrency < 4` or WebGL capability check) and fall back to a static gradient/image.
- Max one heavy 3D scene mounted at a time (hero only) — never stack multiple R3F canvases on one route.
- Framer Motion animations use `transform`/`opacity` only (GPU-accelerated), never animate `width`/`height`/`top`/`left` directly.
- All animated list/table views (holdings, screener results) use virtualization (`@tanstack/react-virtual`) beyond 50 rows.
- **Reduced-motion scope broadened (gap identified in review):** the `prefers-reduced-motion` check applies platform-wide per §6.5, not only to 3D scenes as originally scoped — 2D micro-interactions, GSAP hero choreography, and scroll-linked parallax are exactly the animations most likely to trigger vestibular discomfort (WCAG 2.3.3) and were previously unguarded.
- **Measurable performance budget (gap identified in review — rules were qualitative only):** target sustained ≥50fps during the hero animation sequence on a CPU-throttled-4x/mid-tier-mobile Chrome DevTools profile; verified manually at Phase 5 sign-off (Document 8) until an automated Lighthouse/WebPageTest FPS check is added to CI.

### 6.7 Progressive Web App — Scope Decision (gap identified in review)

The original C4 diagram (Document 1 §2.3) labeled the client layer "Next.js 15 Web App | PWA | (future) Mobile via React Native" with zero corresponding architecture anywhere else in the blueprint — a labeled box with no substance, which would mislead phase planning. **Decision: PWA is explicitly out of scope for the Phase 1-10 roadmap** (Document 8) and is removed from the Document 1 diagram accordingly. It is recorded here as a post-launch ADR candidate (Document 8 §23 ADR process) rather than implied committed scope — if pursued later, it requires its own architecture pass covering: Web App Manifest, service worker caching strategy (cache-first for static shell, network-first for API), and critically, a defined behavior for the WS-dependent real-time layer (§7.6 in Doc 3) when offline (a "stale data, last updated Xm ago" banner rather than either failing silently or pretending to be live).

---

*End of Document 2. Continuing in Document 3: Backend Architecture and Database Design.*
