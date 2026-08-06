from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

try:
    from fastapi import FastAPI, HTTPException
except ImportError:                                   
    raise SystemExit(
        "FastAPI is an OPTIONAL layer and is not installed.\n"
        "Install the extras first:\n"
        "    python3 -m pip install -r requirements-extras.txt\n"
        "then start the server with:\n"
        "    uvicorn api.main:app --reload\n"
        "    (or simply: python3 api/main.py)")

from src.config import load_config
from src.clients.base import SourceUnavailable
from src.clients.ustreasury import USTreasuryClient
from src.clients.ecb import ECBClient
from src.clients.worldbank import WorldBankClient
from src.analytics import yield_curve as yc
from src.analytics.fx import fx_metrics
from src.analytics.scorecard import scorecard
from src import history

CFG = load_config()

app = FastAPI(
    title="Macro Pulse API",
    description="Macro analytics on official data sources only "
                "(US Treasury, ECB, World Bank, ...). Cache-backed.",
    version="2.0.0",
)


def _df_json(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    return out.where(pd.notnull(out), None).to_dict(orient="records")


@app.get("/")
def root():
    return {"endpoints": ["/yield-curve", "/yield-curve/episodes",
                          "/fx", "/stress-index", "/history/{metric}"]}


@app.get("/yield-curve")
def yield_curve(latest_only: bool = True):
    try:
        curve = USTreasuryClient().yield_curve(CFG["treasury_years"])
    except SourceUnavailable as exc:
        raise HTTPException(503, str(exc))
    if latest_only:
        curve = curve[curve["date"] == curve["date"].max()]
    return _df_json(curve)


@app.get("/yield-curve/episodes")
def episodes():
    try:
        curve = USTreasuryClient().yield_curve(CFG["treasury_years"])
    except SourceUnavailable as exc:
        raise HTTPException(503, str(exc))
    spread_df = yc.spreads(curve)
    out = {}
    for col in spread_df.columns:
        eps = yc.inversion_episodes(spread_df[col])
        out[col] = _df_json(eps) if not eps.empty else []
    return out


@app.get("/fx")
def fx():
    try:
        data = ECBClient().fx_daily(CFG["fx_currencies"],
                                    start=CFG["fx_start"])
    except SourceUnavailable as exc:
        raise HTTPException(503, str(exc))
    return _df_json(fx_metrics(data))


@app.get("/stress-index")
def stress_index():
    try:
        indicators = {c: tuple(v) for c, v in CFG["wb_indicators"].items()}
        wb = WorldBankClient().all_indicators(
            CFG["countries"], date_range=CFG["wb_range"],
            indicators=indicators)
    except SourceUnavailable as exc:
        raise HTTPException(503, str(exc))
    return _df_json(scorecard(wb))


@app.get("/history/{metric}")
def metric_history(metric: str):
    df = history.load_metric(metric, CFG["history"]["db_path"])
    if df.empty:
        raise HTTPException(404, f"no recorded history for '{metric}'")
    return _df_json(df)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
