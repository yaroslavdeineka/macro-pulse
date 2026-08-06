from __future__ import annotations

import pandas as pd


def debt_panel(wb_long: pd.DataFrame) -> pd.DataFrame:
    """One row per country: latest debt/GDP, g, r, r-g, and a verdict.

    Requires wb_long to include indicators govt_debt_gdp_pct,
    gdp_growth_pct and (optionally) real_interest_pct.
    """
    need = {"govt_debt_gdp_pct", "gdp_growth_pct"}
    have = set(wb_long["indicator"].unique())
    if not need.issubset(have):
        return pd.DataFrame()
    rows = []
    for (iso3, country), grp in wb_long.groupby(["country_iso3", "country"]):
        row = {"country_iso3": iso3, "country": country}
        for ind in ("govt_debt_gdp_pct", "gdp_growth_pct", "real_interest_pct"):
            sub = (grp[grp["indicator"] == ind]
                   .dropna(subset=["value"]).sort_values("year"))
            if sub.empty:
                row[ind] = None
                continue
            row[ind] = round(float(sub["value"].iloc[-1]), 1)
            row[f"{ind}_year"] = int(sub["year"].iloc[-1])
        g, r, debt = (row.get("gdp_growth_pct"), row.get("real_interest_pct"),
                      row.get("govt_debt_gdp_pct"))
        if g is not None and r is not None:
            row["r_minus_g_pp"] = round(r - g, 1)
            if r > g and (debt or 0) > 60:
                row["verdict"] = "snowball risk (r>g, debt>60%)"
            elif r > g:
                row["verdict"] = "r>g — watch"
            else:
                row["verdict"] = "g>r — growing out"
        else:
            row["r_minus_g_pp"] = None
            row["verdict"] = "insufficient data"
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("govt_debt_gdp_pct",
                           ascending=False, na_position="last"
                           ).reset_index(drop=True)
