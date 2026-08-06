"""National Bank of Ukraine — open data API (official, no key).

Docs: https://bank.gov.ua/ua/open-data/api-dev
Calls:
  https://bank.gov.ua/NBU_Exchange/exchange_site
      ?start=YYYYMMDD&end=YYYYMMDD&valcode=usd&sort=exchangedate
      &order=asc&json                       — official UAH rate history
  https://bank.gov.ua/NBUStatService/v1/statdirectory/monetary?json
      — monetary aggregates incl. the key policy rate

The only source in the panel covering an economy under acute,
war-driven stress — which is what makes the Macro Stress Index results
here genuinely interesting rather than illustrative.
"""

from __future__ import annotations

import json

import pandas as pd

from .base import BaseClient

EXCHANGE_URL = "https://bank.gov.ua/NBU_Exchange/exchange_site"
MONETARY_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/monetary"


class NBUClient(BaseClient):
    source_name = "nbu"

    def uah_rate(self, valcode: str = "usd",
                 start: str = "20150101", end: str = "20991231",
                 refresh: bool = False) -> pd.DataFrame:
        """Official UAH exchange-rate history. Returns: date | currency | rate."""
        params = {"start": start, "end": end, "valcode": valcode,
                  "sort": "exchangedate", "order": "asc", "json": ""}
        text = self.fetch_or_cache(f"uah_{valcode}.json", EXCHANGE_URL,
                                   params=params, refresh=refresh)
        return self.parse_exchange(text)

    @staticmethod
    def parse_exchange(text: str) -> pd.DataFrame:
        rows = json.loads(text)
        if not isinstance(rows, list) or not rows:
            raise ValueError("NBU exchange: unexpected/empty payload")
        df = pd.DataFrame(rows)
        date_col = "exchangedate" if "exchangedate" in df else "date"
        cc_col = "cc" if "cc" in df else "currency"
        # 'rate' is quoted PER `units` (100 USD before ~2020, 1 after);
        # 'rate_per_unit' is always normalised — prefer it, else divide.
        if "rate_per_unit" in df:
            rate = pd.to_numeric(df["rate_per_unit"], errors="coerce")
        else:
            rate = (pd.to_numeric(df["rate"], errors="coerce")
                    / pd.to_numeric(df.get("units", 1), errors="coerce")
                        .fillna(1))
        out = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], dayfirst=True, errors="coerce"),
            "currency": df[cc_col].astype(str).str.upper(),
            "rate": rate,
        })
        return (out.dropna().sort_values("date").reset_index(drop=True))

    def monetary_aggregates(self, refresh: bool = False) -> pd.DataFrame:
        """Monthly monetary aggregates (M0..M3, UAH mn) from the
        statdirectory. Returns tidy: date | aggregate | value."""
        text = self.fetch_or_cache("monetary.json", MONETARY_URL,
                                   params={"json": ""}, refresh=refresh)
        return self.parse_monetary(text)

    @staticmethod
    def parse_monetary(text: str) -> pd.DataFrame:
        rows = json.loads(text)
        df = pd.DataFrame(rows)
        need = {"dt", "id_api", "value"}
        if not need.issubset(df.columns):
            raise ValueError(f"NBU monetary: missing {need - set(df.columns)}")
        df = df[df["id_api"].isin(["M0", "M1", "M2", "M3"])]
        out = pd.DataFrame({
            "date": pd.to_datetime(df["dt"].astype(str), format="%Y%m%d",
                                   errors="coerce"),
            "aggregate": df["id_api"],
            "value": pd.to_numeric(df["value"], errors="coerce"),
        })
        return (out.dropna().sort_values(["aggregate", "date"])
                   .reset_index(drop=True))
