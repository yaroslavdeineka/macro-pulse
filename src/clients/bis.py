from __future__ import annotations

import io

import pandas as pd

from .base import BaseClient
from ..schemas import validate

BASE_URL = "https://stats.bis.org/api/v1/data"

#: ISO3 -> ISO2 area codes, the form the BIS flow keys expect
ISO3_TO_ISO2 = {
    "USA": "US", "GBR": "GB", "DEU": "DE", "POL": "PL", "UKR": "UA",
    "JPN": "JP", "FRA": "FR", "ITA": "IT", "ESP": "ES", "TUR": "TR",
}


class BISClient(BaseClient):
    source_name = "bis"

    def credit_gap(self, countries_iso3: list[str], start: str = "2000",
                   refresh: bool = False) -> pd.DataFrame:
        """Quarterly credit-to-GDP gap. Returns: date | geo | value."""
        iso2 = [ISO3_TO_ISO2[c] for c in countries_iso3 if c in ISO3_TO_ISO2]
        key = f"Q.{'+'.join(iso2)}.P.A.C"
        url = f"{BASE_URL}/WS_CREDIT_GAP/{key}/all"
        cache_key = f"credit_gap_{'_'.join(sorted(iso2))}.csv"
        text = self.fetch_or_cache(cache_key, url,
                                   params={"format": "csv",
                                           "startPeriod": start},
                                   refresh=refresh)
        return validate(self.parse_csv(text), "monthly_indicator", "bis")

    @staticmethod
    def parse_csv(text: str) -> pd.DataFrame:
        """BIS SDMX-CSV: find TIME_PERIOD / OBS_VALUE / reference-area
        columns BY NAME — the exact column set varies by flow."""
        raw = pd.read_csv(io.StringIO(text))
        raw.columns = [c.strip().upper() for c in raw.columns]
        time_col = next((c for c in raw.columns if "TIME_PERIOD" in c), None)
        val_col = next((c for c in raw.columns if "OBS_VALUE" in c), None)
        geo_col = next((c for c in raw.columns
                        if c in ("BORROWERS_CTY", "REF_AREA", "COUNTRY")), None)
        if not time_col or not val_col:
            raise ValueError("BIS CSV: TIME_PERIOD/OBS_VALUE not found")
        df = pd.DataFrame({
            # quarterly periods arrive as "2024-Q3"
            "date": pd.PeriodIndex(raw[time_col].astype(str),
                                   freq="Q").to_timestamp(how="end").normalize(),
            "geo": raw[geo_col] if geo_col else "??",
            "value": pd.to_numeric(raw[val_col], errors="coerce"),
        })
        return (df.dropna(subset=["value"])
                  .sort_values(["geo", "date"]).reset_index(drop=True))
