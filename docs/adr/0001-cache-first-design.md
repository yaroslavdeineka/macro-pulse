# ADR-0001: Cache-first, live-refresh data layer

**Date:** 2025-12 · **Status:** accepted

## Context
Official statistical APIs are free but not always up; the pipeline
should still run for someone who just cloned it, with no setup and no
dependency on every source being reachable at that moment.

## Decision
Every successful fetch is written to `data/cache/` as the RAW response
body. Default runs read cache; `--refresh` forces live pulls; network
failure falls back to stale cache with a logged warning.

## Consequences
+ Fully offline-runnable demo; cache files double as verifiable snapshots.
+ Raw-body caching means parsers are exercised identically live/offline.
- Cache can go stale silently if refresh is never run → mitigated by the
  scheduled GitHub Actions refresh (ADR-0005).
