from __future__ import annotations

import pandas as pd

#: currency -> ISO3 of the issuing economy (for CPI lookup)
CCY_TO_ISO3 = {"USD": "USA", "GBP": "GBR", "PLN": "POL", "JPY": "JPN",
               "CHF": "CHE", "TRY": "TUR", "CZK": "CZE", "HUF": "HUN",
               "SEK": "SWE", "NOK": "NOR"}
EUR_ISO3 = "DEU"   # pragmatic euro-area proxy when only country CPIs exist


def annual_cpi_index(wb_long: pd.DataFrame) -> pd.DataFrame:
    """Build a CPI *index* per country from WB inflation rates (annual %).

    Compounds inflation_pct into a level index (base year = 100).
    Returns: country_iso3 | year | cpi_index.
    """
    infl = wb_long[wb_long["indicator"] == "inflation_pct"].copy()
    if infl.empty:
        return pd.DataFrame(columns=["country_iso3", "year", "cpi_index"])
    out = []
    for iso3, grp in infl.groupby("country_iso3"):
        grp = grp.dropna(subset=["value"]).sort_values("year")
        idx = (1 + grp["value"].astype(float) / 100).cumprod() * 100
        out.append(pd.DataFrame({"country_iso3": iso3,
                                 "year": grp["year"].values,
                                 "cpi_index": idx.values}))
    return pd.concat(out, ignore_index=True)


def real_fx_index(fx: pd.DataFrame, wb_long: pd.DataFrame) -> pd.DataFrame:
    """Real exchange-rate index per currency vs EUR, start = 100.

    Input fx: date | currency | rate (units of ccy per 1 EUR).
    Returns tidy: date | currency | nominal_idx | real_idx.
    """
    cpi = annual_cpi_index(wb_long)
    if cpi.empty or fx.empty:
        return pd.DataFrame()
    base_cpi = cpi[cpi["country_iso3"] == EUR_ISO3].set_index("year")["cpi_index"]
    frames = []
    for ccy, grp in fx.groupby("currency"):
        iso3 = CCY_TO_ISO3.get(ccy)
        if iso3 is None:
            continue
        f_cpi = cpi[cpi["country_iso3"] == iso3].set_index("year")["cpi_index"]
        if f_cpi.empty or base_cpi.empty:
            continue
        g = grp.sort_values("date").copy()
        g["year"] = g["date"].dt.year
        g["cpi_f"] = g["year"].map(f_cpi)
        g["cpi_b"] = g["year"].map(base_cpi)
        g = g.dropna(subset=["cpi_f", "cpi_b"])
        if g.empty:
            continue
        # rate is ccy per EUR -> real appreciation of ccy = nominal
        # appreciation adjusted by relative price levels
        real = g["rate"] * (g["cpi_b"] / g["cpi_f"])
        g["nominal_idx"] = g["rate"] / g["rate"].iloc[0] * 100
        g["real_idx"] = real / real.iloc[0] * 100
        frames.append(g[["date", "currency", "nominal_idx", "real_idx"]])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def real_fx_summary(rfx: pd.DataFrame) -> pd.DataFrame:
    """One row per currency: nominal vs real change over the period.
    The gap between the two is the inflation differential."""
    if rfx.empty:
        return pd.DataFrame()
    rows = []
    for ccy, g in rfx.groupby("currency"):
        g = g.sort_values("date")
        rows.append({
            "currency": ccy,
            "period": f"{g['date'].iloc[0].date()} → {g['date'].iloc[-1].date()}",
            "nominal_change_pct": round(float(g["nominal_idx"].iloc[-1] - 100), 1),
            "real_change_pct": round(float(g["real_idx"].iloc[-1] - 100), 1),
            "inflation_gap_pp": round(float(g["real_idx"].iloc[-1]
                                            - g["nominal_idx"].iloc[-1]), 1),
        })
    return pd.DataFrame(rows)
