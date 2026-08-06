# Architecture Decision Records

One file per decision, immutable once accepted. To change a decision, write a new ADR that
supersedes the old one — never edit history.

Format: Context → Decision → Consequences → Alternatives rejected.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-stack.md) | Python/FastAPI backend, React+MapLibre PWA frontend | Accepted |
| [0002](0002-tiles-from-postgis.md) | Serve vector tiles directly from PostGIS | Accepted |
| [0003](0003-append-only-observations.md) | Append-only observations with derived status | Accepted — schema v1, writers v2 |
| [0004](0004-open-feed-spec.md) | Publish MBFS, an open GBFS-like feed spec | Accepted — drafted v1, published v2 |
| [0005](0005-availability-as-a-plugin.md) | Availability out of v1, behind a provider seam | Accepted |
