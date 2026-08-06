from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def fx_metrics(fx: pd.DataFrame, vol_window: int = 30) -> pd.DataFrame:
    """Input tidy: date | currency | rate.  Output: one summary row per currency."""
    rows = []
    for ccy, grp in fx.groupby("currency"):
        s = grp.set_index("date")["rate"].sort_index()
        ret = np.log(s).diff().dropna()
        roll_vol = ret.rolling(vol_window).std() * np.sqrt(TRADING_DAYS) * 100
        peak = s.cummax()
        drawdown = (s / peak - 1) * 100
        z = (s.iloc[-1] - s.mean()) / s.std() if s.std() > 0 else np.nan
        rows.append({
            "currency": ccy,
            "obs": len(s),
            "first": s.index.min().date(),
            "last": s.index.max().date(),
            "latest_rate": round(float(s.iloc[-1]), 4),
            "period_change_pct": round(float(s.iloc[-1] / s.iloc[0] - 1) * 100, 2),
            "ann_vol_30d_pct": round(float(roll_vol.iloc[-1]), 2)
                               if not np.isnan(roll_vol.iloc[-1]) else None,
            "max_drawdown_pct": round(float(drawdown.min()), 2),
            "level_zscore": round(float(z), 2),
        })
    return pd.DataFrame(rows)


def fx_timeseries(fx: pd.DataFrame, vol_window: int = 30) -> pd.DataFrame:
    """Per-day series for plotting: date | currency | rate | roll_vol_pct."""
    out = []
    for ccy, grp in fx.groupby("currency"):
        s = grp.set_index("date")["rate"].sort_index()
        ret = np.log(s).diff()
        roll_vol = ret.rolling(vol_window).std() * np.sqrt(TRADING_DAYS) * 100
        df = pd.DataFrame({"rate": s, "roll_vol_pct": roll_vol})
        df["currency"] = ccy
        out.append(df.reset_index())
    return pd.concat(out, ignore_index=True)
