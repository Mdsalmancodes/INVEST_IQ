"""application-layer services for the portfolio bounded context.

Per docs/architecture/02-clean-architecture-folder-frontend.md §4.1:
application services orchestrate domain objects and depend on domain-layer
repository Protocols only, never on infrastructure directly. The founder's
Phase 3 requirement enumerates the calculations implemented in
PortfolioCalculationService below; standard financial formulas are used
throughout since the frozen architecture docs do not prescribe exact
formulas for these (unlike, e.g., Document 4 §10's ML pipeline outputs).
"""
