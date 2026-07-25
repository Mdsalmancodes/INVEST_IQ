"""Local-filesystem-backed repository implementations for the AI/ML
bounded context — disclosed substitutes for the frozen architecture's
S3-compatible object storage (model artifacts) and MongoDB (prediction
run records); see docs/phase-7/known-issues.md. Both are built behind the
same domain-layer repository Protocols, so swapping to real object
storage/Mongo later is an infrastructure-only change.
"""
