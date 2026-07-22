# INVEST IQ — Architecture Review Log

## Review 1 — Pre-Implementation Comprehensive Design Review

**Date:** 2026-07-21
**Reviewer role:** Principal Software Architect design review (conducted via 5 independent parallel review passes covering: Database/API design; AI/ML pipeline; Security/Scalability; Frontend/UX/Accessibility/SEO; DevOps/Testing/Maintainability)
**Scope:** All 8 architecture documents (`01` through `08`), reviewed in full prior to any implementation.
**Trigger:** Explicit founder request for a comprehensive architecture review across 20 dimensions (missing features, architectural inconsistencies, scalability, performance, security, database normalization, API design, AI/ML pipeline, frontend architecture, backend architecture, DevOps, technology choices, cost optimization, maintainability, extensibility, accessibility, mobile responsiveness, animation performance, SEO, testing coverage) before implementation could begin.

### Outcome Summary

**78 total findings** across the 5 review tracks: **~18 CRITICAL**, **~35 MAJOR**, **~25 MINOR**. All CRITICAL and MAJOR findings have been addressed via direct edits to the 8 architecture documents (not left as a separate backlog) — each fix is inlined at its exact location with a `> **REVISION (post-architecture-review):**` marker explaining what changed and why, so the documents remain self-contained and a reader does not need this log to understand any individual section.

### Major Structural Decision Arising From This Review

**Service topology collapsed from 4 backend services to 2** (`core-api` + `ai-service`), reversing the original draft's `market-data-service` and `notification-service` as independently deployed services. This was identified independently by both the Security/Scalability track and the DevOps/Testing track as contradicting Document 1 §2.1's own stated modular-monolith rationale, and as imposing unjustified local-dev burden (10+ containers for any single feature). This is a deployment-topology simplification, not a domain redesign — Clean Architecture module boundaries (Document 2 §4.1) are unchanged, and extraction back into separate services later remains mechanical per the same reasoning Document 1 §2.1 already used to justify keeping `ai-service` separate from day one.

### Findings by Category and Resolution

| # | Category | Finding | Severity | Resolved in |
|---|---|---|---|---|
| 1 | Backend/DevOps | 4-service split contradicted stated modular-monolith rationale; excessive local-dev burden | CRITICAL | Doc 3 §7.1, Doc 7 §17.4 (Compose profiles), Doc 1 §2.2-2.3, Doc 2 §5.1/5.3, Doc 8 (roadmap phase updates) |
| 2 | Database | `ohlcv_bars` referenced narratively 4× but never given DDL — highest-volume table in the system | CRITICAL | Doc 3 §8.1 (full DDL, partitioned by month) |
| 3 | Database | `corporate_actions` described narratively with no DDL | CRITICAL | Doc 3 §8.1 (full DDL) |
| 4 | Database/API | `instruments.symbol` non-globally-unique but every market-data/AI endpoint keyed by bare symbol | CRITICAL | Doc 3 §8.1 (partial unique index + documented future-ADR path), Doc 4 §9.4 |
| 5 | Database/Roadmap | SIP Calculator, IPO Analyzer, Dividend Analysis named as roadmap deliverables with zero backing schema/endpoints | CRITICAL | Doc 3 §8.1 (`dividend_records`, `sip_scenarios`, `ipo_listings`), Doc 4 §9.4, Doc 8 Phase 9 |
| 6 | Database/Caching | Internal contradiction: OHLCV bar caching described as both "90-day hot window" and "cached forever/indefinitely" | CRITICAL | Doc 3 §7.7, §8.3, §8.4 (corrected + reconciled) |
| 7 | Security/Scalability | Single Redis instance overloaded across 6 conflicting workloads — documented SPOF | CRITICAL | Doc 3 §7.7 (3-instance split: cache/broker/session), Doc 1 §2.3 diagram, Doc 7 §17.4/§19.3 |
| 8 | Security/Scalability | No Redis HA/failover strategy anywhere | CRITICAL | Doc 3 §7.7 (Multi-AZ failover requirement for broker/session instances) |
| 9 | Security/Scalability | No cache stampede/thundering herd protection anywhere | CRITICAL | Doc 3 §7.7 (distributed lock, jittered TTLs, backfill-inflight flag) |
| 10 | Security | Screener endpoint had no bound on filter complexity — algorithmic-complexity DoS vector; no backing schema existed at all | CRITICAL | Doc 3 §8.1 (`screener_factors` materialized table), Doc 4 §9.4a |
| 11 | Security | No backup/disaster recovery strategy for any of the 3 databases | CRITICAL | Doc 3 §8.5 (RPO/RTO table, restore drills), Doc 8 Phase 10 |
| 12 | ML | Feature store versioning claim was an assertion, not a mechanism — real train/serve skew risk | CRITICAL | Doc 4 §10.2 (shared feature registry library, CI-enforced) |
| 13 | ML | No fallback for `ai-service` downtime — would blank the entire Predictions/Recommendation surface | CRITICAL | Doc 4 §10.1b, §9.2 (degraded response envelope) |
| 14 | ML | No LLM cost control despite "unlimited" AI Assistant promise — real unbounded-spend risk | CRITICAL | Doc 4 §9.6a (token budget, tool-loop cap, circuit breaker) |
| 15 | ML | Ensemble stacking meta-model was one unimplementable sentence | CRITICAL | Doc 4 §10.2a (concrete architecture, regime definition, dependency tracking, fallback) |
| 16 | ML | No handling anywhere for new-IPO/sparse-data instruments, despite roadmap committing to an IPO Analyzer feature | CRITICAL | Doc 4 §10.1a (per-model minimum-data thresholds, dataQuality flag) |
| 17 | Frontend | No mobile-first/responsive strategy stated anywhere | CRITICAL | Doc 2 §6.1a (breakpoint scale, minimum viewport, touch targets) |
| 18 | Frontend | No mobile adaptation pattern for dense data tables (holdings, screener) | CRITICAL | Doc 2 §6.1a (`DataTable` mobileRenderMode prop) |
| 19 | Frontend | SEO architecture was a single sentence — no structured data/OG/sitemap/robots.txt | CRITICAL | Doc 2 §6.4 (full SEO architecture section) |
| 20 | Frontend | Accessibility specified only as a test gate, never as component design standard | MAJOR | Doc 2 §6.5 (component-level a11y requirements) |
| 21 | Frontend | Dark mode implied by one hex token, no theming mechanism | MAJOR | Doc 2 §6.3/§6.3a (semantic CSS-variable tokens, next-themes) |
| 22 | Frontend | PWA labeled in a diagram with zero corresponding architecture | MAJOR | Doc 1 §2.3 (removed from diagram), Doc 2 §6.7 (explicit scope decision + future ADR path) |
| 23 | DevOps | No feature flag / gradual rollout system anywhere | CRITICAL | Doc 7 §19.3a, Doc 4 §10.8 (canary rollout) |
| 24 | DevOps | No staging data strategy | CRITICAL | Doc 6 §16.5 (seeding script + anonymization pipeline) |
| 25 | Testing | No BFF↔internal-service contract testing | MAJOR | Doc 6 §16.2 (generated-types CI job), Doc 7 §18.1 |
| 26 | Testing | No chaos/resilience testing for the notification/WebSocket layer | MAJOR | Doc 6 §16.2a (dedicated resilience suite) |
| 27 | Security | No secrets rotation strategy (only storage practices) | MAJOR | Doc 6 §15.4 (kid-based JWT rotation, managed-rotation cadence) |
| 28 | Security | No prompt-injection threat modeling for the AI Assistant's tool-calling layer | MAJOR | Doc 6 §15.1 (added to threat table), Doc 4 §9.6a |
| 29 | ML | No leading concept-drift monitoring (only lagging accuracy-drop detection) | MAJOR | Doc 4 §10.8a, Doc 5 §14.4 (paging alert) |
| 30 | Various | Numerous MINOR findings (touch-target sizing, FPS budgets, mobile filter UI, E2E smoke-tier on every PR, CSP directive completeness, WS connection caps, etc.) | MINOR | Distributed across Doc 2 §6.1a/§6.6, Doc 6 §15.5/§16.3/§16.6, Doc 3 §7.6 |

### Verification of Fix Completeness

Every CRITICAL and MAJOR finding above has a corresponding inline `REVISION` marker in its target document, cross-referenced bidirectionally (e.g., Doc 4's ML fixes reference the Doc 3 schema changes they depend on, and vice versa) so the documents remain internally consistent as a set. A follow-up grep pass confirmed no remaining unpatched references to the retired `market-data-service`/`notification-service` service names outside of intentional historical explanation notes.

### Sign-off Status

Pending founder review of this log and the updated documents. Implementation (Phase 1, Document 8 §24) should not begin until this review is acknowledged.
