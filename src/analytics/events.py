from __future__ import annotations

import pandas as pd

#: FOMC decision (statement) days
FOMC_DATES = [
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
    "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    "2026-09-16", "2026-10-28", "2026-12-09",
]

#: ECB monetary-policy decision days
ECB_DATES = [
    "2024-01-25", "2024-03-07", "2024-04-11", "2024-06-06", "2024-07-18",
    "2024-09-12", "2024-10-17", "2024-12-12",
    "2025-01-30", "2025-03-06", "2025-04-17", "2025-06-05", "2025-07-24",
    "2025-09-11", "2025-10-30", "2025-12-18",
    "2026-02-05", "2026-03-19", "2026-04-30", "2026-06-11", "2026-07-23",
    "2026-09-10", "2026-10-29", "2026-12-17",
]

CALENDAR = {"FOMC": FOMC_DATES, "ECB": ECB_DATES}


def event_moves(series: pd.Series, events: list[str], window: int = 3,
                label: str = "") -> pd.DataFrame:
    """Change in `series` from `window` obs before to `window` obs after
    each event date that falls inside the series' span.

    Returns: event | date | before | after | move (same units as series).
    Uses positional offsets on the series' own (trading-day) index, so
    weekends/holidays are handled implicitly.
    """
    s = series.dropna().sort_index()
    if s.empty:
        return pd.DataFrame()
    rows = []
    for d in pd.to_datetime(events):
        if not (s.index.min() <= d <= s.index.max()):
            continue
        pos = s.index.searchsorted(d)
        lo, hi = pos - window, pos + window
        if lo < 0 or hi >= len(s):
            continue
        before, after = float(s.iloc[lo]), float(s.iloc[hi])
        rows.append({"event": label, "date": d.date(),
                     "before": round(before, 2), "after": round(after, 2),
                     "move": round(after - before, 2)})
    return pd.DataFrame(rows)


def curve_event_study(spread: pd.Series, window: int = 3) -> pd.DataFrame:
    """FOMC decisions vs the 10Y-3M spread (bp)."""
    return event_moves(spread, FOMC_DATES, window, label="FOMC")


def fx_event_study(fx_ts: pd.DataFrame, currency: str = "USD",
                   window: int = 3) -> pd.DataFrame:
    """ECB decisions vs an ECB reference rate (level move, %)."""
    grp = fx_ts[fx_ts["currency"] == currency]
    s = grp.set_index("date")["rate"].sort_index()
    out = event_moves(s * 100 / s.iloc[0] if len(s) else s,
                      ECB_DATES, window, label=f"ECB vs EUR/{currency}")
    return out
