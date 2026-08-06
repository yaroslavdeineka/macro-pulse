from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"

DEFAULTS: dict[str, Any] = {
    "countries": ["USA", "GBR", "DEU", "POL", "UKR"],
    "fx_currencies": ["USD", "GBP"],
    "treasury_years": [2024],
    "fx_start": "2015-01-01",
    "wb_range": "1990:2026",
    "eurostat_periods": 120,
    "boe_date_from": "01/Jan/2000",
    "wb_indicators": {
        "FP.CPI.TOTL.ZG": ["inflation_pct", 1],
        "NY.GDP.MKTP.KD.ZG": ["gdp_growth_pct", -1],
        "SL.UEM.TOTL.ZS": ["unemployment_pct", 1],
    },
    "analytics": {
        "inversion_min_days": 3,
        "fx_vol_window": 30,
        "event_window_days": 3,
        "nowcast_horizon_days": 5,
        "backtest_duration_years": 9.0,
    },
    "thresholds": {"stress_alert": 1.0, "inversion_alert": True},
    "history": {"enabled": True, "db_path": "data/history.duckdb"},
    "alerts": {},
    "fred": {"api_key_env": "FRED_API_KEY", "series": []},
}


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config.yaml merged over DEFAULTS (shallow per top-level key)."""
    cfg = copy.deepcopy(DEFAULTS)
    p = path or CONFIG_PATH
    if p.exists():
        user = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for key, value in user.items():
            cfg[key] = value
    return cfg
