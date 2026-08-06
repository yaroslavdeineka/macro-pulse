# ADR-0005: Scheduled self-refresh via GitHub Actions

**Date:** 2026-07 · **Status:** accepted

## Context
A snapshot repo decays as soon as it is published; the data should
keep itself current without anyone remembering to re-run the pipeline.

## Decision
`.github/workflows/refresh.yml` runs `--refresh` every weekday 06:30
UTC and commits `data/` + `outputs/` only when content changed. Bot
commits are labelled `data: scheduled refresh YYYY-MM-DD`.

## Consequences
+ Every cache file becomes a dated, CI-committed, verifiable snapshot.
+ DuckDB run history accumulates a real time series.
- Bot commits don't count toward a personal contribution graph; the
  point is fresh data, not activity.
