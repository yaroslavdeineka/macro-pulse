from __future__ import annotations

import io

import pandas as pd

from .base import BaseClient
from ..schemas import validate

BASE_URL = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI"


class IMFClient(BaseClient):
    source_name = "imf"

    def __init__(self, timeout: int | None = None):
        super().__init__(timeout)
        # without this Accept header the endpoint answers in SDMX-XML
        self.session.headers["Accept"] = "application/vnd.sdmx.data+csv"

    def cpi_monthly(self, countries_iso3: list[str], start: str = "2000",
                    refresh: bool = False) -> pd.DataFrame:
        """Monthly headline CPI index per country. Returns: date | geo | value."""
        key = f"{'+'.join(countries_iso3)}.CPI._T.IX.M"
        url = f"{BASE_URL}/{key}"
        cache_key = f"cpi_{'_'.join(sorted(countries_iso3))}.csv"
        text = self.fetch_or_cache(cache_key, url,
                                   params={"startPeriod": start},
                                   refresh=refresh)
        return validate(self.parse_sdmx_csv(text), "monthly_indicator", "imf")

    @staticmethod
    def parse_sdmx_csv(text: str) -> pd.DataFrame:
        df = pd.read_csv(io.StringIO(text), dtype=str)
        need = {"COUNTRY", "TIME_PERIOD", "OBS_VALUE"}
        if not need.issubset(df.columns):
            raise ValueError(
                f"IMF SDMX-CSV: expected columns {sorted(need)}, "
                f"got {list(df.columns)[:8]}")
        df = df.dropna(subset=["COUNTRY", "TIME_PERIOD", "OBS_VALUE"])
        if "FREQUENCY" in df.columns:
            df = df[df["FREQUENCY"] == "M"]
        out = pd.DataFrame({
            # monthly periods come as e.g. "2026-M05"
            "date": pd.to_datetime(
                df["TIME_PERIOD"].str.replace("-M", "-", regex=False),
                errors="coerce"),
            "geo": df["COUNTRY"],
            "value": pd.to_numeric(df["OBS_VALUE"], errors="coerce"),
        })
        return (out.dropna(subset=["date", "value"])
                   .sort_values(["geo", "date"]).reset_index(drop=True))
