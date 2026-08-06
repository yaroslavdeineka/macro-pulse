from __future__ import annotations

import io

import pandas as pd

from .base import BaseClient

IADB_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"


class BankOfEnglandClient(BaseClient):
    source_name = "boe"

    def bank_rate(self, date_from: str = "01/Jan/2015",
                  refresh: bool = False) -> pd.DataFrame:
        """Official Bank Rate. Returns: date | rate_pct."""
        params = {
            "csv.x": "yes",
            "Datefrom": date_from,
            "Dateto": "now",
            "SeriesCodes": "IUDBEDR",
            "CSVF": "TN",          # titles + numbers layout
            "UsingCodes": "Y",
            "VPD": "Y",
            "VFD": "N",
        }
        text = self.fetch_or_cache("bank_rate.csv", IADB_URL,
                                   params=params, refresh=refresh)
        return self.parse_csv(text)

    @staticmethod
    def parse_csv(text: str) -> pd.DataFrame:
        raw = pd.read_csv(io.StringIO(text))
        raw.columns = [c.strip().upper() for c in raw.columns]
        date_col = next((c for c in raw.columns if "DATE" in c), raw.columns[0])
        val_col = next((c for c in raw.columns if "IUDBEDR" in c), raw.columns[-1])
        out = pd.DataFrame({
            "date": pd.to_datetime(raw[date_col], dayfirst=True, errors="coerce"),
            "rate_pct": pd.to_numeric(raw[val_col], errors="coerce"),
        })
        return out.dropna().sort_values("date").reset_index(drop=True)
