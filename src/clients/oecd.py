"""OECD — public SDMX REST API (official, no key).

Docs: https://data.oecd.org/api/ (SDMX-CSV via sdmx.oecd.org)
Call: https://sdmx.oecd.org/public/rest/data/{agency},{flow},{ver}/{key}

Series used:
  DSD_STES@DF_CLI — Composite Leading Indicator (amplitude-adjusted,
  monthly). An independent "is this economy turning?" cross-check
  against the World Bank scorecard.

Status: experimental — the OECD moved from stats.oecd.org to
sdmx.oecd.org in 2024 and dataflow ids can still change; the pipeline
treats this section as optional.
"""

from __future__ import annotations

import io

import pandas as pd

from .base import BaseClient
from ..schemas import validate

BASE_URL = "https://sdmx.oecd.org/public/rest/data"
FLOW = "OECD.SDD.STES,DSD_STES@DF_CLI,4.1"


class OECDClient(BaseClient):
    source_name = "oecd"

    def cli(self, countries_iso3: list[str], start: str = "2000-01",
            refresh: bool = False) -> pd.DataFrame:
        """Composite Leading Indicator. Returns: date | geo | value."""
        key = f"{'+'.join(countries_iso3)}.M.LI...AA...H"
        url = f"{BASE_URL}/{FLOW}/{key}"
        cache_key = f"cli_{'_'.join(sorted(countries_iso3))}.csv"
        text = self.fetch_or_cache(cache_key, url,
                                   params={"format": "csvfile",
                                           "startPeriod": start},
                                   refresh=refresh)
        return validate(self.parse_csv(text), "monthly_indicator", "oecd")

    @staticmethod
    def parse_csv(text: str) -> pd.DataFrame:
        raw = pd.read_csv(io.StringIO(text))
        raw.columns = [c.strip().upper() for c in raw.columns]
        time_col = next((c for c in raw.columns if "TIME_PERIOD" in c), None)
        val_col = next((c for c in raw.columns if "OBS_VALUE" in c), None)
        geo_col = next((c for c in raw.columns if c == "REF_AREA"), None)
        if not time_col or not val_col:
            raise ValueError("OECD CSV: TIME_PERIOD/OBS_VALUE not found")
        df = pd.DataFrame({
            "date": pd.to_datetime(raw[time_col], errors="coerce"),
            "geo": raw[geo_col] if geo_col else "??",
            "value": pd.to_numeric(raw[val_col], errors="coerce"),
        })
        return (df.dropna(subset=["date", "value"])
                  .sort_values(["geo", "date"]).reset_index(drop=True))
