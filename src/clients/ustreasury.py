"""U.S. Department of the Treasury — Daily Par Yield Curve Rates (CMT).

Source (official, no API key):
  https://home.treasury.gov/resource-center/data-chart-center/interest-rates/
CSV endpoint pattern (one file per calendar year):
  .../daily-treasury-rates.csv/{YEAR}/all?field_tdr_date_value={YEAR}
      &type=daily_treasury_yield_curve&page=&_format=csv

Column layout: Date + a set of tenor columns ("1 Mo" ... "30 Yr").
The tenor set changes over time (e.g. "1.5 Month" was added on
2025-02-18), so parsing is done by column NAME, never by position.
"""

from __future__ import annotations

import io

import pandas as pd

from .base import BaseClient, SourceUnavailable
from ..schemas import validate

CSV_URL = ("https://home.treasury.gov/resource-center/data-chart-center/"
           "interest-rates/daily-treasury-rates.csv/{year}/all")

#: canonical tenor labels -> maturity in years (used for curve plotting)
TENOR_YEARS = {
    "1 Mo": 1 / 12, "1.5 Month": 1.5 / 12, "2 Mo": 2 / 12, "3 Mo": 0.25,
    "4 Mo": 4 / 12, "6 Mo": 0.5, "1 Yr": 1, "2 Yr": 2, "3 Yr": 3,
    "5 Yr": 5, "7 Yr": 7, "10 Yr": 10, "20 Yr": 20, "30 Yr": 30,
}


class USTreasuryClient(BaseClient):
    source_name = "ustreasury"

    def yield_curve(self, years: list[int], refresh: bool = False) -> pd.DataFrame:
        """Return a tidy frame: date | tenor | maturity_years | yield_pct.

        Years that can be fetched neither live nor from cache are skipped
        with a warning — one unreachable year must not blank a decade of
        curve history. Raises only if NO year loads at all."""
        frames, missing = [], []
        for year in years:
            key = f"yield_curve_{year}.csv"
            url = CSV_URL.format(year=year)
            params = {"field_tdr_date_value": year,
                      "type": "daily_treasury_yield_curve",
                      "page": "", "_format": "csv"}
            try:
                text = self.fetch_or_cache(key, url, params=params,
                                           refresh=refresh)
                frames.append(self.parse_csv(text))
            except SourceUnavailable:
                missing.append(year)
        if not frames:
            raise SourceUnavailable(
                f"ustreasury: no data for any requested year {years}")
        if missing:
            print(f"  [ustreasury] years unavailable this run: {missing}")
        out = pd.concat(frames, ignore_index=True)
        out = out.sort_values(["date", "maturity_years"]).reset_index(drop=True)
        return validate(out, "yield_curve", "ustreasury")

    @staticmethod
    def parse_csv(text: str) -> pd.DataFrame:
        raw = pd.read_csv(io.StringIO(text))
        raw.columns = [c.strip() for c in raw.columns]
        if "Date" not in raw.columns:
            raise ValueError("US Treasury CSV: 'Date' column not found")
        tenor_cols = [c for c in raw.columns if c in TENOR_YEARS]
        long = raw.melt(id_vars="Date", value_vars=tenor_cols,
                        var_name="tenor", value_name="yield_pct")
        long["date"] = pd.to_datetime(long["Date"], format="%m/%d/%Y")
        long["maturity_years"] = long["tenor"].map(TENOR_YEARS)
        long["yield_pct"] = pd.to_numeric(long["yield_pct"], errors="coerce")
        return (long.drop(columns="Date")
                    .dropna(subset=["yield_pct"])
                    .reset_index(drop=True))
