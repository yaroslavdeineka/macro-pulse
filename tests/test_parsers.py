import json
from pathlib import Path

import pandas as pd
import pytest

from src.clients.ustreasury import USTreasuryClient
from src.clients.ecb import ECBClient
from src.clients.worldbank import WorldBankClient
from src.clients.bankofengland import BankOfEnglandClient
from src.analytics import yield_curve as yc
from src.analytics.fx import fx_metrics
from src.analytics.scorecard import scorecard

BASE = Path(__file__).resolve().parents[1]
REAL_TREASURY = BASE / "data" / "cache" / "ustreasury_yield_curve_2024.csv"


# ---------------------------------------------------------------- Treasury
def test_treasury_parse_real_snapshot():
    df = USTreasuryClient.parse_csv(REAL_TREASURY.read_text())
    assert set(df.columns) == {"tenor", "yield_pct", "date", "maturity_years"}
    assert df["date"].min() == pd.Timestamp("2024-01-02")
    assert df["date"].max() == pd.Timestamp("2024-12-31")
    # spot-check a known official value: 12/31/2024 10 Yr = 4.58
    v = df[(df.date == "2024-12-31") & (df.tenor == "10 Yr")]["yield_pct"].iloc[0]
    assert v == pytest.approx(4.58)


def test_inversion_episode_detection_on_real_2024_data():
    df = USTreasuryClient.parse_csv(REAL_TREASURY.read_text())
    sp = yc.spreads(df)
    eps = yc.inversion_episodes(sp["spread_10y_3m_bp"])
    # 2024 opened deep in the post-2022 inversion and dis-inverted in December
    assert not eps.empty
    assert eps.iloc[0]["start"] == pd.Timestamp("2024-01-02").date()
    assert eps.iloc[-1]["end"] >= pd.Timestamp("2024-12-01").date()
    assert eps.iloc[0]["min_bp"] < -100  # the inversion was >100bp deep


def test_curve_snapshots_shape():
    df = USTreasuryClient.parse_csv(REAL_TREASURY.read_text())
    snaps = yc.latest_curve_snapshots(df)
    assert snaps["snapshot"].nunique() == 3
    assert (snaps.groupby("snapshot")["tenor"].count() >= 10).all()


# --------------------------------------------------------------------- ECB
ECB_FIXTURE = """KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-06-01,1.0842
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-06-02,1.0867
EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,SP00,A,2026-06-01,0.8511
EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,SP00,A,2026-06-02,0.8523
"""


def test_ecb_sdmx_csv_parser():
    df = ECBClient.parse_sdmx_csv(ECB_FIXTURE, value_name="rate",
                                  dim_col="CURRENCY", dim_name="currency")
    assert len(df) == 4
    assert set(df["currency"]) == {"USD", "GBP"}
    assert df["rate"].between(0.5, 2).all()
    m = fx_metrics(df)
    assert set(m["currency"]) == {"USD", "GBP"}


# --------------------------------------------------------------- World Bank
WB_FIXTURE = json.dumps([
    {"page": 1, "pages": 1, "per_page": 1000, "total": 4},
    [
        {"indicator": {"id": "FP.CPI.TOTL.ZG"}, "country": {"id": "GB", "value": "United Kingdom"},
         "countryiso3code": "GBR", "date": "2024", "value": 2.53},
        {"indicator": {"id": "FP.CPI.TOTL.ZG"}, "country": {"id": "GB", "value": "United Kingdom"},
         "countryiso3code": "GBR", "date": "2023", "value": 7.31},
        {"indicator": {"id": "FP.CPI.TOTL.ZG"}, "country": {"id": "PL", "value": "Poland"},
         "countryiso3code": "POL", "date": "2024", "value": 3.72},
        {"indicator": {"id": "FP.CPI.TOTL.ZG"}, "country": {"id": "PL", "value": "Poland"},
         "countryiso3code": "POL", "date": "2023", "value": None},
    ],
])


def test_worldbank_parser_drops_nulls_and_sorts():
    df = WorldBankClient.parse_json(WB_FIXTURE)
    assert len(df) == 3            # the null value row is dropped
    assert list(df.columns) == ["country_iso3", "country", "year", "value"]
    assert df.iloc[0]["year"] <= df.iloc[1]["year"]


def test_worldbank_parser_raises_on_error_payload():
    err = json.dumps([{"message": [{"id": "120", "value": "Invalid indicator"}]}])
    with pytest.raises(ValueError):
        WorldBankClient.parse_json(err)


def test_scorecard_composite_direction():
    wb = pd.DataFrame({
        "country_iso3": ["AAA"] * 6,
        "country": ["Testland"] * 6,
        "year": [2022, 2023, 2024] * 2,
        "indicator": ["inflation_pct"] * 3 + ["gdp_growth_pct"] * 3,
        # inflation spikes in the latest year; growth collapses
        "value": [2.0, 2.1, 9.0, 3.0, 2.9, -4.0],
    })
    sc = scorecard(wb)
    assert sc.iloc[0]["stress_index"] > 0.5   # clearly stressed


# ------------------------------------------------------------ Bank of England
BOE_FIXTURE = """DATE,IUDBEDR
01 Jan 2024,5.25
01 Feb 2024,5.25
01 Aug 2024,5.00
"""


def test_boe_parser():
    df = BankOfEnglandClient.parse_csv(BOE_FIXTURE)
    assert len(df) == 3
    assert df["rate_pct"].iloc[-1] == 5.00
    assert df["date"].is_monotonic_increasing
