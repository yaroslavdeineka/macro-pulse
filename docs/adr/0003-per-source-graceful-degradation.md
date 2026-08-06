# ADR-0003: Per-source graceful degradation

**Date:** 2025-12 · **Status:** accepted

## Context
With 10+ independent sources, some endpoint is almost always down or
slow. One dead endpoint must not blank the whole monitor.

## Decision
Each report section runs in isolation; failures append the section to a
"skipped" list and the report still builds. Derived analytics declare
prerequisites and skip cleanly when base data is missing.

## Consequences
+ The report always builds; a skipped section is a one-line note, not
  a crash.
- Requires discipline: sections communicate only via the shared ctx dict.
