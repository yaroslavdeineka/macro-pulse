# ADR-0007: Backtest uses simulated bond returns

**Date:** 2026-07 · **Status:** accepted

## Context
The curve-signal backtest needs investable returns, but official
sources publish yields, not total-return indices. Importing equity or
TR data from non-official sources would break ADR-0002.

## Decision
Simulate 10Y note returns via a constant-duration approximation
(r ≈ carry − D·Δy) and 3M-bill carry for cash. Every rendering of the
result (report, dashboard, README) carries an illustrative-only
disclaimer with the methodology stated inline.

## Consequences
+ Tear-sheet workflow (CAGR/Sharpe/drawdown/underwater) demonstrated
  end-to-end without compromising the official-sources rule.
- Numbers are approximations: no convexity, roll-down, or costs.
