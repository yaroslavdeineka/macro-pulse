# ADR-0004: Parse by column name, never by position

**Date:** 2025-12 · **Status:** accepted

## Context
Treasury added a "1.5 Month" tenor in Feb 2025; SDMX-CSV column sets
vary with the `detail` parameter; BIS/OECD flows reshape between
versions.

## Decision
All parsers locate columns by NAME (or documented JSON keys), validated
against declared schemas (src/schemas.py) at parse time.

## Consequences
+ Survived the 2025 Treasury tenor addition with zero changes.
+ Schema drift fails loudly at the source, not cryptically downstream.
