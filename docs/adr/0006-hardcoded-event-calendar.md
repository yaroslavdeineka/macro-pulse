# ADR-0006: Hardcoded central-bank decision calendar

**Date:** 2026-07 · **Status:** accepted

## Context
The event study needs FOMC/ECB decision dates. They could be scraped
from press-release feeds.

## Decision
Hardcode the dates (public, small in number, static history) in
src/analytics/events.py, extended by hand when each year's schedule
is published.

## Consequences
+ No scraping and nothing to break — consistent with ADR-0002.
- Needs a small manual update once a year. The report now prints a
  note when the data extends past the last calendar entry, so a
  stale calendar can't go unnoticed.
