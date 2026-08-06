import json

import numpy as np
import pandas as pd
import pytest

from src.config import load_config, DEFAULTS
from src.schemas import validate, SchemaError
from src.clients.imf import IMFClient
from src.clients.eurostat import EurostatClient
from src.clients.bis import BISClient
from src.clients.oecd import OECDClient
from src.clients.nbu import NBUClient
from src.clients.fred import FREDClient
from src.analytics import events, nowcast, correlations
from src.analytics import backtest as bt
from src.analytics.real_fx import annual_cpi_index, real_fx_index
from src.analytics.debt import debt_panel
from src import alerts


# config
def test_config_loads_and_merges():
    cfg = load_config()
    assert set(DEFAULTS).issubset(cfg)
    assert len(cfg["countries"]) >= 5
    assert cfg["analytics"]["inversion_min_days"] >= 1


#  schemas
def test_schema_catches_missing_column():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "rate": [1.0]})
    with pytest.raises(SchemaError):
        validate(df, "fx", "test")         


def test_schema_catches_wrong_dtype():
    df = pd.DataFrame({"date": ["not-a-date"], "currency": ["USD"],
                       "rate": [1.0]})
    with pytest.raises(SchemaError):
        validate(df, "fx", "test")



IMF_FIXTURE = """DATAFLOW,COUNTRY,INDEX_TYPE,COICOP_1999,TYPE_OF_TRANSFORMATION,FREQUENCY,TIME_PERIOD,OBS_VALUE
IMF.STA:CPI(5.0.0),,,,,,,
IMF.STA:CPI(5.0.0),USA,CPI,_T,IX,M,2026-M04,152.72
IMF.STA:CPI(5.0.0),USA,CPI,_T,IX,M,2026-M05,153.69
IMF.STA:CPI(5.0.0),USA,CPI,_T,IX,Q,2026-Q1,150.15
IMF.STA:CPI(5.0.0),DEU,CPI,_T,IX,M,2026-M05,121.4
"""


def test_imf_drops_metadata_and_quarterly_rows():
    df = IMFClient.parse_sdmx_csv(IMF_FIXTURE)
    assert set(df.columns) == {"date", "geo", "value"}
    assert len(df) == 3                      
    assert set(df["geo"]) == {"USA", "DEU"}
    assert df["date"].max() == pd.Timestamp("2026-05-01")
    assert df[df.geo == "USA"]["value"].iloc[-1] == pytest.approx(153.69)


# Eurostat
EUROSTAT_FIXTURE = json.dumps({
    "id": ["freq", "geo", "time"], "size": [1, 2, 2],
    "dimension": {
        "freq": {"category": {"index": {"M": 0}}},
        "geo": {"category": {"index": {"DE": 0, "PL": 1}}},
        "time": {"category": {"index": {"2025-11": 0, "2025-12": 1}}},
    },
    "value": {"0": 2.2, "1": 2.4, "2": 4.7, "3": 4.9},
})


def test_eurostat_jsonstat_unflattens_correctly():
    df = EurostatClient.parse_jsonstat(EUROSTAT_FIXTURE)
    assert len(df) == 4
    de_dec = df[(df.geo == "DE") & (df.date == "2025-12-01")]["value"].iloc[0]
    pl_nov = df[(df.geo == "PL") & (df.date == "2025-11-01")]["value"].iloc[0]
    assert de_dec == pytest.approx(2.4)
    assert pl_nov == pytest.approx(4.7)


#  BIS
BIS_FIXTURE = """FREQ,BORROWERS_CTY,TIME_PERIOD,OBS_VALUE
Q,US,2025-Q3,-6.1
Q,US,2025-Q4,-5.8
Q,GB,2025-Q4,-11.2
"""


def test_bis_parses_quarterly_periods():
    df = BISClient.parse_csv(BIS_FIXTURE)
    assert len(df) == 3
    assert df[df.geo == "US"]["value"].iloc[-1] == pytest.approx(-5.8)
    assert df["date"].max() == pd.Timestamp("2025-12-31")


# OECD
OECD_FIXTURE = """REF_AREA,FREQ,TIME_PERIOD,OBS_VALUE
USA,M,2025-11,99.6
USA,M,2025-12,99.8
DEU,M,2025-12,100.3
"""


def test_oecd_parses_by_name():
    df = OECDClient.parse_csv(OECD_FIXTURE)
    assert len(df) == 3
    assert df[df.geo == "DEU"]["value"].iloc[0] == pytest.approx(100.3)


# NBU
NBU_FIXTURE = json.dumps([
    {"exchangedate": "01.01.2019", "cc": "USD", "rate": 2768.83,
     "units": 100, "rate_per_unit": 27.6883},
    {"exchangedate": "01.06.2026", "cc": "USD", "rate": 41.95,
     "units": 1, "rate_per_unit": 41.95},
    {"exchangedate": "02.06.2026", "cc": "USD", "rate": 42.10,
     "units": 1, "rate_per_unit": 42.10},
])


def test_nbu_parses_exchange_history():
    df = NBUClient.parse_exchange(NBU_FIXTURE)
    assert list(df.columns) == ["date", "currency", "rate"]
    assert df["rate"].iloc[-1] == pytest.approx(42.10)
    # pre-2020 quotes come per 100 USD — must be normalised per unit
    assert df["rate"].iloc[0] == pytest.approx(27.6883)
    assert df["date"].iloc[0] == pd.Timestamp("2019-01-01")


# FRED
FRED_FIXTURE = json.dumps({"observations": [
    {"date": "2025-12-01", "value": "4.33"},
    {"date": "2026-01-01", "value": "."},        # FRED's NaN marker
    {"date": "2026-02-01", "value": "4.08"},
]})


def test_fred_drops_dot_values():
    df = FREDClient.parse_json(FRED_FIXTURE)
    assert len(df) == 2
    assert df["value"].iloc[-1] == pytest.approx(4.08)


#event study
def test_event_moves_positional_window():
    idx = pd.bdate_range("2024-09-02", periods=20)
    s = pd.Series(np.arange(20.0), index=idx)     
    table = events.event_moves(s, ["2024-09-18"], window=3, label="FOMC")
    assert len(table) == 1
    assert table["move"].iloc[0] == pytest.approx(6.0)   


def test_event_outside_span_is_skipped():
    idx = pd.bdate_range("2024-01-02", periods=10)
    s = pd.Series(1.0, index=idx)
    assert events.event_moves(s, ["2030-01-01"], 3).empty


# nowcast
def test_holt_tracks_linear_trend():
    idx = pd.bdate_range("2025-01-01", periods=100)
    s = pd.Series(np.linspace(0, 99, 100), index=idx)   
    res = nowcast.holt_forecast(s, horizon=5)
    assert res
    assert res["forecast"]["value"].iloc[-1] == pytest.approx(104, abs=3)
    assert res["rmse"] < res["naive_rmse"] * 2


def test_holt_needs_history():
    assert nowcast.holt_forecast(pd.Series([1.0, 2.0])) == {}


# correlations
def test_correlation_of_identical_changes_is_one():
    idx = pd.bdate_range("2025-01-01", periods=120)
    rng = np.random.default_rng(0)
    a = pd.Series(rng.normal(size=120).cumsum(), index=idx)
    named = {"a": a, "b": a * 2 + 5, "noise": pd.Series(
        rng.normal(size=120).cumsum(), index=idx)}
    corr = correlations.correlation_matrix(named)
    assert corr.loc["a", "b"] == pytest.approx(1.0)
    top = correlations.strongest_pairs(corr, top=1)
    assert top["pair"].iloc[0] == "a × b"


# ----------------------------------------------------------------- backtest
def _toy_market(n=500, seed=1):
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(seed)
    y10 = pd.Series(3 + rng.normal(0, 0.02, n).cumsum(), index=idx).clip(0.5)
    y3m = y10 - np.concatenate([np.full(n // 2, 1.0),
                                np.full(n - n // 2, -0.5)])  # invert 2nd half
    spread = (y10 - y3m) * 100
    return spread, y10, pd.Series(y3m, index=idx)


def test_backtest_produces_full_tear_sheet():
    spread, y10, y3m = _toy_market()
    res = bt.run_backtest(spread, y10, y3m)
    assert res
    assert {"strategy", "buy_and_hold_10y", "cash"} == set(res["curves"].columns)
    assert "sharpe" in res["stats"].columns
    assert 0 < res["time_in_cash_pct"] < 100


def test_backtest_signal_is_lagged():
    """No lookahead: strategy return on day t uses day t-1's signal."""
    spread, y10, y3m = _toy_market()
    res = bt.run_backtest(spread, y10, y3m)
    flip = spread[spread < 0].index[0]           
    pos = res["curves"].index.searchsorted(flip)
    assert pos > 0   


# real fx
def _wb_fixture():
    rows = []
    for iso3, infl in [("USA", 3.0), ("DEU", 2.0)]:
        for year in range(2020, 2026):
            rows.append({"country_iso3": iso3, "country": iso3,
                         "year": year, "value": infl,
                         "indicator": "inflation_pct"})
    return pd.DataFrame(rows)


def test_cpi_index_compounds():
    cpi = annual_cpi_index(_wb_fixture())
    usa = cpi[cpi.country_iso3 == "USA"].sort_values("year")
    assert usa["cpi_index"].iloc[-1] / usa["cpi_index"].iloc[0] == \
        pytest.approx(1.03 ** 5, rel=1e-6)


def test_real_fx_diverges_from_nominal_with_inflation_gap():
    fx = pd.DataFrame({
        "date": pd.to_datetime([f"{y}-06-01" for y in range(2020, 2026)]),
        "currency": "USD",
        "rate": 1.10,                            
    })
    rfx = real_fx_index(fx, _wb_fixture())
    assert not rfx.empty
    assert rfx["real_idx"].iloc[-1] < 100
    assert rfx["nominal_idx"].iloc[-1] == pytest.approx(100)


# debt panel
def test_debt_panel_verdicts():
    rows = []
    for iso3, debt, g, r in [("ITA", 140, 0.8, 2.5), ("POL", 50, 3.5, 1.0)]:
        for ind, val in [("govt_debt_gdp_pct", debt),
                         ("gdp_growth_pct", g), ("real_interest_pct", r)]:
            rows.append({"country_iso3": iso3, "country": iso3,
                         "year": 2024, "value": val, "indicator": ind})
    panel = debt_panel(pd.DataFrame(rows))
    ita = panel[panel.country == "ITA"].iloc[0]
    pol = panel[panel.country == "POL"].iloc[0]
    assert "snowball" in ita["verdict"]
    assert "growing out" in pol["verdict"]


# alerts
def test_alert_fires_only_for_ongoing_inversion():
    eps = pd.DataFrame([{"start": pd.Timestamp("2026-05-01").date(),
                         "end": pd.Timestamp("2026-06-30").date(),
                         "trading_days": 40, "min_bp": -35.0}])
    live = alerts.compose_alerts(eps, pd.Timestamp("2026-06-30"), None)
    stale = alerts.compose_alerts(eps, pd.Timestamp("2026-12-31"), None)
    assert len(live) == 1 and "INVERTED" in live[0]
    assert stale == []


def test_alert_fires_on_stress_threshold():
    sc = pd.DataFrame([{"country": "Ukraine", "stress_index": 1.8},
                       {"country": "Poland", "stress_index": 0.2}])
    msgs = alerts.compose_alerts(None, None, sc, stress_threshold=1.0)
    assert len(msgs) == 1 and "Ukraine" in msgs[0]


# history
def test_history_roundtrip(tmp_path):
    duckdb = pytest.importorskip("duckdb")        
    from src import history
    db = tmp_path / "h.duckdb"
    n = history.record_run(
        [{"metric": "stress_index", "entity": "UKR",
          "as_of": pd.Timestamp("2026-07-01").date(), "value": 1.5}], db)
    assert n == 1
    df = history.load_metric("stress_index", db)
    assert len(df) == 1 and df["value"].iloc[0] == pytest.approx(1.5)
    assert history.run_count(db) == 1


NBU_MONETARY_FIXTURE = json.dumps([
    {"dt": "20250101", "id_api": "M3", "txten": "Monetary aggregate M3",
     "freq": "M", "value": 100.0},
    {"dt": "20260101", "id_api": "M3", "txten": "Monetary aggregate M3",
     "freq": "M", "value": 118.0},
    {"dt": "20260101", "id_api": "XX", "txten": "other", "freq": "M",
     "value": 5.0},
])


def test_nbu_monetary_filters_aggregates():
    df = NBUClient.parse_monetary(NBU_MONETARY_FIXTURE)
    assert set(df["aggregate"]) == {"M3"}
    assert len(df) == 2
    assert df["value"].iloc[-1] == pytest.approx(118.0)


#charts
def test_chart_geo_lines_writes_png():
    from src import report
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2025-02-01"] * 2),
        "geo": ["DE", "DE", "PL", "PL"],
        "value": [2.1, 2.2, 4.5, 4.4],
    })
    path = report.chart_geo_lines(df, "t", "y", "test_chart.png")
    assert path.exists() and path.stat().st_size > 1000
    import contextlib
    with contextlib.suppress(OSError):   
        path.unlink()


def test_chart_curve_heatmap_writes_png():
    from src import report
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    rows = [{"date": d, "tenor": t, "maturity_years": m, "yield_pct": y}
            for d in dates
            for t, m, y in [("3 Mo", 0.25, 5.4), ("2 Yr", 2.0, 4.3),
                            ("10 Yr", 10.0, 3.9)]]
    path = report.chart_curve_heatmap(pd.DataFrame(rows))
    assert path.exists() and path.stat().st_size > 1000
