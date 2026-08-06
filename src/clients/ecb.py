from __future__ import annotations

import io

import pandas as pd

from .base import BaseClient
from ..schemas import validate

BASE_URL = "https://data-api.ecb.europa.eu/service/data"


class ECBClient(BaseClient):
    source_name = "ecb"

    def fx_daily(self, currencies: list[str], start: str,
                 refresh: bool = False) -> pd.DataFrame:
        """Daily EUR reference rates. Returns: date | currency | rate."""
        key = "+".join(sorted(currencies))
        cache_key = f"fx_{key.replace('+', '_')}.csv"
        url = f"{BASE_URL}/EXR/D.{key}.EUR.SP00.A"
        params = {"format": "csvdata", "detail": "dataonly", "startPeriod": start}
        text = self.fetch_or_cache(cache_key, url, params=params, refresh=refresh)
        return validate(self.parse_sdmx_csv(text, value_name="rate",
                                            dim_col="CURRENCY",
                                            dim_name="currency"),
                        "fx", "ecb")

    def deposit_facility_rate(self, start: str, refresh: bool = False) -> pd.DataFrame:
        """ECB deposit facility rate. Returns: date | rate_pct."""
        url = f"{BASE_URL}/FM/D.U2.EUR.4F.KR.DFR.LEV"
        params = {"format": "csvdata", "detail": "dataonly", "startPeriod": start}
        text = self.fetch_or_cache("dfr.csv", url, params=params, refresh=refresh)
        df = self.parse_sdmx_csv(text, value_name="rate_pct")
        return df[["date", "rate_pct"]]

    @staticmethod
    def parse_sdmx_csv(text: str, value_name: str = "value",
                       dim_col: str | None = None,
                       dim_name: str | None = None) -> pd.DataFrame:
        raw = pd.read_csv(io.StringIO(text))
        required = {"TIME_PERIOD", "OBS_VALUE"}
        if not required.issubset(raw.columns):
            raise ValueError(f"ECB SDMX-CSV: missing {required - set(raw.columns)}")
        out = pd.DataFrame({
            "date": pd.to_datetime(raw["TIME_PERIOD"]),
            value_name: pd.to_numeric(raw["OBS_VALUE"], errors="coerce"),
        })
        if dim_col and dim_col in raw.columns:
            out[dim_name or dim_col.lower()] = raw[dim_col]
        return out.dropna(subset=[value_name]).sort_values("date").reset_index(drop=True)
