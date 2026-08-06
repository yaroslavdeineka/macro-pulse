from __future__ import annotations

import numpy as np
import pandas as pd


def holt_forecast(series: pd.Series, horizon: int = 5,
                  alpha: float = 0.3, beta: float = 0.1) -> dict:
    """Holt (level+trend) smoothing; returns forecast + diagnostics.

    Returns dict with: forecast (DataFrame step|value|lo95|hi95),
    fitted RMSE, last actual value, naive-model RMSE for comparison.
    """
    s = series.dropna().astype(float)
    if len(s) < 20:
        return {}
    level, trend = s.iloc[0], s.iloc[1] - s.iloc[0]
    fitted = []
    for y in s.iloc[1:]:
        prev_level = level
        fitted.append(level + trend)
        level = alpha * y + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    fitted = np.array(fitted)
    actual = s.iloc[1:].to_numpy()
    resid = actual - fitted
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    naive_rmse = float(np.sqrt(np.mean(np.diff(s) ** 2)))
    band = 1.96 * rmse
    rows = [{"step": h,
             "value": round(level + h * trend, 2),
             "lo95": round(level + h * trend - band * np.sqrt(h), 2),
             "hi95": round(level + h * trend + band * np.sqrt(h), 2)}
            for h in range(1, horizon + 1)]
    return {"forecast": pd.DataFrame(rows),
            "rmse": round(rmse, 2),
            "naive_rmse": round(naive_rmse, 2),
            "last_actual": round(float(s.iloc[-1]), 2),
            "last_date": s.index[-1]}


def nowcast_lines(result: dict, name: str, unit: str) -> list[str]:
    """Render a nowcast dict into report markdown lines."""
    if not result:
        return []
    f = result["forecast"]
    lines = [
        f"**{name} — illustrative {len(f)}-step nowcast** "
        f"(Holt exponential smoothing):",
        "",
        f"- last actual: **{result['last_actual']} {unit}** "
        f"({pd.Timestamp(result['last_date']).date()})",
        f"- {len(f)}-step forecast: **{f['value'].iloc[-1]} {unit}** "
        f"(95% band {f['lo95'].iloc[-1]} … {f['hi95'].iloc[-1]})",
        f"- in-sample RMSE {result['rmse']} vs naive-model RMSE "
        f"{result['naive_rmse']} — "
        + ("the smoother barely beats naive; treat as illustrative."
           if result["rmse"] >= 0.9 * result["naive_rmse"]
           else "modest edge over naive persistence."),
        "",
        "*Not a trading model — a workflow demo with an explicit "
        "naive benchmark.*",
        "",
    ]
    return lines
