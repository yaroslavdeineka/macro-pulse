from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def simulate_bond_returns(y10: pd.Series, duration: float = 9.0) -> pd.Series:
    """Daily total-return proxy for a constant-maturity 10Y note:
    carry (y/252) minus duration times the daily yield change."""
    y = y10.dropna().astype(float) / 100
    dy = y.diff()
    ret = y.shift() / TRADING_DAYS - duration * dy
    return ret.dropna()


def cash_returns(y3m: pd.Series) -> pd.Series:
    """Daily return of rolling 3M bills ≈ yield/252 (carry only)."""
    y = y3m.dropna().astype(float) / 100
    return (y.shift() / TRADING_DAYS).dropna()


def run_backtest(spread_bp: pd.Series, y10: pd.Series, y3m: pd.Series,
                 duration: float = 9.0) -> dict:
    """Strategy: hold the 10Y note; switch to cash while 10Y-3M < 0.
    Signal lagged one day (no lookahead). Benchmark: buy-and-hold 10Y.

    Returns dict with equity curves, stats table, and drawdown series.
    """
    bond = simulate_bond_returns(y10, duration)
    cash = cash_returns(y3m)
    sig = (spread_bp.dropna() >= 0).astype(int).shift(1)   # 1 = risk-on
    df = pd.DataFrame({"bond": bond, "cash": cash, "sig": sig}).dropna()
    if len(df) < 60:
        return {}
    df["strategy"] = np.where(df["sig"] == 1, df["bond"], df["cash"])
    curves = pd.DataFrame({
        "strategy": (1 + df["strategy"]).cumprod(),
        "buy_and_hold_10y": (1 + df["bond"]).cumprod(),
        "cash": (1 + df["cash"]).cumprod(),
    }, index=df.index)
    stats = pd.DataFrame([_stats(df[c], curves[k])
                          for c, k in [("strategy", "strategy"),
                                       ("bond", "buy_and_hold_10y"),
                                       ("cash", "cash")]],
                         index=["curve-signal strategy",
                                "buy & hold 10Y (proxy)", "cash (3M bills)"])
    dd = curves["strategy"] / curves["strategy"].cummax() - 1
    time_in_cash = float((df["sig"] == 0).mean()) * 100
    return {"curves": curves, "stats": stats, "drawdown": dd,
            "time_in_cash_pct": round(time_in_cash, 1),
            "n_days": len(df)}


def _stats(daily: pd.Series, curve: pd.Series) -> dict:
    years = len(daily) / TRADING_DAYS
    cagr = float(curve.iloc[-1] ** (1 / years) - 1) * 100 if years > 0 else np.nan
    vol = float(daily.std() * np.sqrt(TRADING_DAYS)) * 100
    sharpe = float(daily.mean() / daily.std() * np.sqrt(TRADING_DAYS)) \
        if daily.std() > 0 else np.nan
    maxdd = float((curve / curve.cummax() - 1).min()) * 100
    return {"CAGR_pct": round(cagr, 2), "ann_vol_pct": round(vol, 2),
            "sharpe": round(sharpe, 2), "max_drawdown_pct": round(maxdd, 2),
            "total_return_pct": round(float(curve.iloc[-1] - 1) * 100, 2)}
