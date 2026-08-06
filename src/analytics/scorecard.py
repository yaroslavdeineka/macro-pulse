from __future__ import annotations

import numpy as np
import pandas as pd

#: indicator -> +1 if HIGH values mean stress, -1 if LOW values mean stress
STRESS_SIGN = {
    "inflation_pct": +1,
    "unemployment_pct": +1,
    "gdp_growth_pct": -1,
}


def scorecard(wb_long: pd.DataFrame,
              stress_signs: dict[str, int] | None = None) -> pd.DataFrame:
    """Input: country | country_iso3 | year | indicator | value (long).

    Output: one row per country with latest values, per-indicator
    z-scores vs own history, and the composite stress index.
    `stress_signs` overrides the module default (injected from config).
    """
    signs = stress_signs or STRESS_SIGN
    rows = []
    for (iso3, country), grp in wb_long.groupby(["country_iso3", "country"]):
        row = {"country_iso3": iso3, "country": country}
        z_parts = []
        for ind, sub in grp.groupby("indicator"):
            sub = sub.dropna(subset=["value"]).sort_values("year")
            if sub.empty:
                continue
            hist = sub["value"].astype(float)
            latest = float(hist.iloc[-1])
            latest_year = int(sub["year"].iloc[-1])
            mu, sd = hist.mean(), hist.std(ddof=1)
            z = (latest - mu) / sd if sd and not np.isnan(sd) and sd > 0 else 0.0
            row[f"{ind}"] = round(latest, 2)
            row[f"{ind}_year"] = latest_year
            row[f"{ind}_z"] = round(z, 2)
            sign = signs.get(ind, 0)
            if sign:
                z_parts.append(sign * z)
        row["stress_index"] = round(float(np.mean(z_parts)), 2) if z_parts else None
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("stress_index", ascending=False).reset_index(drop=True)
