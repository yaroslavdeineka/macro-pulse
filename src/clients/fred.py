from __future__ import annotations

import json
import os

import pandas as pd

from .base import BaseClient, SourceUnavailable

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FREDClient(BaseClient):
    source_name = "fred"

    def __init__(self, api_key_env: str = "FRED_API_KEY", **kw):
        super().__init__(**kw)
        self.api_key = os.environ.get(api_key_env, "")

    def series(self, series_id: str, start: str = "2000-01-01",
               refresh: bool = False) -> pd.DataFrame:
        """One FRED series. Returns: date | value."""
        cache_key = f"{series_id}.json"
        if not self.api_key:
            cached = self.read_cache(cache_key)
            if cached is None:
                raise SourceUnavailable(
                    "fred: FRED_API_KEY not set and no cache exists "
                    "(this source is optional)")
            return self.parse_json(cached)
        params = {"series_id": series_id, "api_key": self.api_key,
                  "file_type": "json", "observation_start": start}
        text = self.fetch_or_cache(cache_key, BASE_URL, params=params,
                                   refresh=refresh)
        return self.parse_json(text)

    def many(self, series_ids: list[str], start: str = "2000-01-01",
             refresh: bool = False) -> pd.DataFrame:
        """Long frame: date | series | value across several series."""
        frames = []
        for sid in series_ids:
            df = self.series(sid, start=start, refresh=refresh)
            df["series"] = sid
            frames.append(df)
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def parse_json(text: str) -> pd.DataFrame:
        payload = json.loads(text)
        obs = payload.get("observations")
        if obs is None:
            raise ValueError(f"FRED: unexpected payload: {str(payload)[:200]}")
        df = pd.DataFrame(obs)[["date", "value"]]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")  # "." -> NaN
        return (df.dropna(subset=["date", "value"])
                  .sort_values("date").reset_index(drop=True))
