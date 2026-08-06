# ADR-0002: Official sources only, keyless by default

**Date:** 2025-12 · **Status:** accepted

## Context
Aggregators (Statista, Trading Economics) repackage primary data behind
paywalls with redistribution-hostile terms.

## Decision
Only official statistical providers, fetched directly. Sources requiring
even a free key (FRED) are strictly OPTIONAL: enabled via env var, never
required for pipeline, tests, or demo.

## Consequences
+ Legally clean redistribution of cached snapshots; full provenance.
+ "Clone and run" needs zero signup.
- Some panels are lower frequency than commercial data (accepted;
  Eurostat/IMF monthly panels close most of the gap).
