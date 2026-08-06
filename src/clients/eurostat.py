from __future__ import annotations

import json

import pandas as pd

from .base import BaseClient
from ..schemas import validate

BASE_URL = ("https://ec.europa.eu/eurostat/api/dissemination/"
            "statistics/1.0/data")

ISO3_TO_EUROSTAT = {"DEU": "DE", "POL": "PL", "FRA": "FR", "ITA": "IT",
                    "ESP": "ES", "GBR": "UK", "TUR": "TR"}


class EurostatClient(BaseClient):
    source_name = "eurostat"

    def hicp_annual_rate(self, countries_iso3: list[str], periods: int = 120,
                         refresh: bool = False) -> pd.DataFrame:
        return self._monthly("prc_hicp_manr", countries_iso3, periods,
                             extra={"coicop": "CP00", "unit": "RCH_A"},
                             refresh=refresh)

    def unemployment_rate(self, countries_iso3: list[str], periods: int = 120,
                          refresh: bool = False) -> pd.DataFrame:
        return self._monthly("une_rt_m", countries_iso3, periods,
                             extra={"s_adj": "SA", "age": "TOTAL",
                                    "sex": "T", "unit": "PC_ACT"},
                             refresh=refresh)

    def _monthly(self, code: str, countries_iso3: list[str], periods: int,
                 extra: dict, refresh: bool) -> pd.DataFrame:
        geos = [ISO3_TO_EUROSTAT[c] for c in countries_iso3
                if c in ISO3_TO_EUROSTAT]
        if not geos:
            raise ValueError("eurostat: no supported countries requested")
        params = {"format": "JSON", "lang": "EN",
                  "lastTimePeriod": periods, **extra}
        # requests encodes list values as repeated geo=DE&geo=PL — what the API wants
        params["geo"] = geos
        cache_key = f"{code}_{'_'.join(sorted(geos))}.json"
        text = self.fetch_or_cache(cache_key, f"{BASE_URL}/{code}",
                                   params=params, refresh=refresh)
        return validate(self.parse_jsonstat(text), "monthly_indicator",
                        "eurostat")

    @staticmethod
    def parse_jsonstat(text: str) -> pd.DataFrame:
        """Minimal JSON-stat 2.0 reader for geo x time datasets."""
        js = json.loads(text)
        if "value" not in js or "dimension" not in js:
            raise ValueError("Eurostat JSON-stat: missing value/dimension")
        dims = js["id"]
        sizes = js["size"]
        geo_idx = js["dimension"]["geo"]["category"]["index"]
        time_idx = js["dimension"]["time"]["category"]["index"]
        geo_pos, time_pos = dims.index("geo"), dims.index("time")
        # stride of each dimension in the flattened value index
        strides = [1] * len(sizes)
        for i in range(len(sizes) - 2, -1, -1):
            strides[i] = strides[i + 1] * sizes[i + 1]
        inv_geo = {v: k for k, v in geo_idx.items()}
        inv_time = {v: k for k, v in time_idx.items()}
        rows = []
        for flat, val in js["value"].items():
            flat = int(flat)
            coords = []
            for size, stride in zip(sizes, strides):
                coords.append((flat // stride) % size)
            rows.append({"geo": inv_geo[coords[geo_pos]],
                         "date": inv_time[coords[time_pos]],
                         "value": val})
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return (df.dropna(subset=["date", "value"])
                  .sort_values(["geo", "date"]).reset_index(drop=True))
