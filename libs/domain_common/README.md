# libs/domain_common

Shared Python value objects and domain primitives used identically by both `apps/core-api` and `apps/ai-service`, installed as an editable package by each service's Poetry project (`poetry add --editable ../../libs/domain_common`).

Per `docs/architecture/03-backend-architecture-database-design.md` §3.4 and §8.1, and `docs/architecture/04-api-design-ai-ml-pipeline.md` §10.2 (feature registry):

- `money.py` — `Money` value object (Decimal-backed, never float — Document 3 §3.4 rule #2)
- `ticker.py` — `Ticker` value object
- `identifiers.py` — `UserId`, `InstrumentId`, etc. (typed UUID wrappers)
- `features/registry.py` — the shared feature-definition registry (content-hashed, semver `featureSetVersion`) imported identically by `apps/ai-service`'s inference code and `ml/training/` — this is what prevents train/serve skew per Document 4 §10.2's revision. **Not yet implemented — Phase 7.**

Populated incrementally as the modules that need each primitive are built (Phase 2 onward for `Money`/`Ticker`/identifiers; Phase 7 for the feature registry).
