# libs/observability

Shared structured-logging setup (JSON logs, automatic secret redaction, `requestId` propagation) used by both backend services, per `docs/architecture/05-data-pipeline-notifications-caching-monitoring.md` §14.1.

Populated starting Phase 1 (this service skeleton) — every service's `/health` and `/ready` endpoints, and every request, log through this shared logger from day one rather than each service inventing its own logging setup.
