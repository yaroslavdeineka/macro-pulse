from __future__ import annotations

import pandas as pd


def to_wide(curve: pd.DataFrame) -> pd.DataFrame:
    """tidy (date|tenor|yield_pct) -> wide (index=date, columns=tenor)."""
    return curve.pivot_table(index="date", columns="tenor",
                             values="yield_pct").sort_index()


def spreads(curve: pd.DataFrame) -> pd.DataFrame:
    """Daily 10Y-2Y and 10Y-3M spreads in basis points."""
    wide = to_wide(curve)
    out = pd.DataFrame(index=wide.index)
    if {"10 Yr", "2 Yr"}.issubset(wide.columns):
        out["spread_10y_2y_bp"] = (wide["10 Yr"] - wide["2 Yr"]) * 100
    if {"10 Yr", "3 Mo"}.issubset(wide.columns):
        out["spread_10y_3m_bp"] = (wide["10 Yr"] - wide["3 Mo"]) * 100
    return out.dropna(how="all")


def inversion_episodes(spread: pd.Series, min_days: int = 3) -> pd.DataFrame:
    """Detect contiguous runs where the spread is below zero.

    Returns one row per episode: start, end, trading_days, min_bp.
    Runs shorter than `min_days` are ignored as noise.
    """
    s = spread.dropna()
    below = s < 0
    # group id increments every time the below/above state flips
    group = (below != below.shift()).cumsum()
    episodes = []
    for _, chunk in s.groupby(group):
        if (chunk < 0).all() and len(chunk) >= min_days:
            episodes.append({
                "start": chunk.index.min().date(),
                "end": chunk.index.max().date(),
                "trading_days": len(chunk),
                "min_bp": round(float(chunk.min()), 1),
            })
    return pd.DataFrame(episodes)


def latest_curve_snapshots(curve: pd.DataFrame,
                           lookbacks: tuple[int, ...] = (0, 126, 251)
                           ) -> pd.DataFrame:
    """Curve shape today vs ~6 months ago vs ~1 year ago (by trading days).

    Returns tidy: snapshot | tenor | maturity_years | yield_pct
    """
    wide = to_wide(curve)
    mat = (curve[["tenor", "maturity_years"]]
           .drop_duplicates().set_index("tenor")["maturity_years"])
    rows = []
    seen_dates = set()
    for lb in lookbacks:
        idx = -(lb + 1) if lb < len(wide) else 0   # clamp to earliest available
        date = wide.index[idx]
        if date in seen_dates:
            continue
        seen_dates.add(date)
        if lb == 0:
            label = "latest"
        elif idx == 0:
            label = "earliest"
        else:
            label = f"-{lb}td"
        snap = wide.loc[date].dropna()
        for tenor, y in snap.items():
            rows.append({"snapshot": f"{label} ({date.date()})",
                         "tenor": tenor,
                         "maturity_years": float(mat[tenor]),
                         "yield_pct": float(y)})
    return (pd.DataFrame(rows)
              .sort_values(["snapshot", "maturity_years"])
              .reset_index(drop=True))
