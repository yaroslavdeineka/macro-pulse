"""World Bank — Indicators API v2 (official, open, no key).

Docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
Call: https://api.worldbank.org/v2/country/{codes}/indicator/{code}
          ?format=json&date=YYYY:YYYY&per_page=N
Response: [ page_metadata, [ {country, countryiso3code, date, value, ...} ] ]
"""

from __future__ import annotations

import json

import pandas as pd

from .base import BaseClient
from ..schemas import validate

BASE_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{code}"

#: indicator code -> (short name, direction of "stress": +1 high is bad, -1 low is bad)
INDICATORS = {
    "FP.CPI.TOTL.ZG":  ("inflation_pct", +1),
    "NY.GDP.MKTP.KD.ZG": ("gdp_growth_pct", -1),
    "SL.UEM.TOTL.ZS":  ("unemployment_pct", +1),
}


class WorldBankClient(BaseClient):
    source_name = "worldbank"

    def indicator(self, countries: list[str], code: str, date_range: str,
                  refresh: bool = False) -> pd.DataFrame:
        """Tidy frame: country_iso3 | country | year | value (one indicator)."""
        cty = ";".join(c.lower() for c in countries)
        cache_key = f"{code}_{'_'.join(sorted(countries))}.json"
        url = BASE_URL.format(countries=cty, code=code)
        params = {"format": "json", "date": date_range, "per_page": 1000}
        text = self.fetch_or_cache(cache_key, url, params=params, refresh=refresh)
        return self.parse_json(text)

    def all_indicators(self, countries: list[str], date_range: str,
                       refresh: bool = False,
                       indicators: dict | None = None) -> pd.DataFrame:
        """Long frame across indicators: country | year | indicator | value.

        `indicators` maps WB code -> (short_name, stress_sign); defaults
        to the module-level INDICATORS, and is normally injected from
        config.yaml by run_monitor."""
        frames = []
        for code, (short, _) in (indicators or INDICATORS).items():
            df = self.indicator(countries, code, date_range, refresh=refresh)
            df["indicator"] = short
            frames.append(df)
        out = pd.concat(frames, ignore_index=True)
        return validate(out, "wb_long", "worldbank")

    @staticmethod
    def parse_json(text: str) -> pd.DataFrame:
        payload = json.loads(text)
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            # The API signals errors as a single-element list with a message
            raise ValueError(f"World Bank API: unexpected payload: {str(payload)[:200]}")
        rows = [
            {
                "country_iso3": obs.get("countryiso3code"),
                "country": (obs.get("country") or {}).get("value"),
                "year": int(obs["date"]),
                "value": obs["value"],
            }
            for obs in payload[1]
            if obs.get("value") is not None and str(obs.get("date", "")).isdigit()
        ]
        return (pd.DataFrame(rows)
                  .sort_values(["country_iso3", "year"])
                  .reset_index(drop=True))
