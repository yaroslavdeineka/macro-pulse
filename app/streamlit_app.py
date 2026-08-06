from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

try:
    import streamlit as st
except ImportError:                                 
    raise SystemExit(
        "Streamlit is an OPTIONAL layer and is not installed.\n"
        "Install the extras first:\n"
        "    python3 -m pip install -r requirements-extras.txt\n"
        "then launch the dashboard with:\n"
        "    streamlit run app/streamlit_app.py")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config                       # noqa: E402
from src.clients.base import SourceUnavailable           # noqa: E402
from src.clients.ustreasury import USTreasuryClient      # noqa: E402
from src.clients.ecb import ECBClient                    # noqa: E402
from src.clients.worldbank import WorldBankClient        # noqa: E402
from src.analytics import yield_curve as yc              # noqa: E402
from src.analytics.fx import fx_metrics, fx_timeseries   # noqa: E402
from src.analytics.scorecard import scorecard            # noqa: E402
from src.analytics import backtest as bt                 # noqa: E402
from src import history                                  # noqa: E402

CFG = load_config()

st.set_page_config(page_title="Macro Pulse", page_icon="📈", layout="wide")
st.title("📈 Macro Pulse")
st.caption("Official data sources only: US Treasury · ECB · World Bank · "
           "IMF · Eurostat · BIS · OECD · NBU · BoE. No scraping, no "
           "third-party aggregators.")

refresh = st.sidebar.button("🔄 Refresh live data")
st.sidebar.markdown("Countries: " + ", ".join(CFG["countries"]))
st.sidebar.markdown("FX pairs: " + ", ".join(
    f"EUR/{c}" for c in CFG["fx_currencies"]))

tab_curve, tab_fx, tab_stress, tab_bt, tab_hist = st.tabs(
    ["Yield curve", "FX", "Stress index", "Toy backtest", "Run history"])

with tab_curve:
    try:
        curve = USTreasuryClient().yield_curve(CFG["treasury_years"],
                                               refresh=refresh)
        spread_df = yc.spreads(curve)
        c1, c2 = st.columns(2)
        latest = spread_df.dropna().iloc[-1]
        c1.metric("10Y − 3M spread", f"{latest.get('spread_10y_3m_bp', float('nan')):.0f} bp")
        c2.metric("10Y − 2Y spread", f"{latest.get('spread_10y_2y_bp', float('nan')):.0f} bp")
        st.line_chart(spread_df)
        eps = yc.inversion_episodes(spread_df.get("spread_10y_3m_bp",
                                                  pd.Series(dtype=float)))
        if not eps.empty:
            st.subheader("Inversion episodes (10Y−3M)")
            st.dataframe(eps, use_container_width=True)
    except SourceUnavailable as exc:
        st.warning(f"Treasury data unavailable: {exc}")

with tab_fx:
    try:
        fx = ECBClient().fx_daily(CFG["fx_currencies"], start=CFG["fx_start"],
                                  refresh=refresh)
        ts = fx_timeseries(fx)
        pick = st.multiselect("Pairs", sorted(ts["currency"].unique()),
                              default=sorted(ts["currency"].unique())[:4])
        wide = (ts[ts["currency"].isin(pick)]
                .pivot_table(index="date", columns="currency", values="rate"))
        st.line_chart(wide / wide.iloc[0] * 100)
        st.subheader("Metrics")
        st.dataframe(fx_metrics(fx), use_container_width=True)
    except SourceUnavailable as exc:
        st.warning(f"ECB data unavailable: {exc} — run refresh once online.")

with tab_stress:
    try:
        indicators = {c: tuple(v) for c, v in CFG["wb_indicators"].items()}
        wb = WorldBankClient().all_indicators(CFG["countries"],
                                              date_range=CFG["wb_range"],
                                              refresh=refresh,
                                              indicators=indicators)
        sc = scorecard(wb)
        st.bar_chart(sc.set_index("country")["stress_index"])
        st.dataframe(sc, use_container_width=True)
    except SourceUnavailable as exc:
        st.warning(f"World Bank data unavailable: {exc} — run refresh once online.")

with tab_bt:
    st.info("ILLUSTRATIVE ONLY — simulated bond returns (duration "
            "approximation), no costs. Demonstrates the tear-sheet "
            "workflow, not an investable strategy.")
    try:
        curve = USTreasuryClient().yield_curve(CFG["treasury_years"])
        spread_df = yc.spreads(curve)
        wide = yc.to_wide(curve)
        res = bt.run_backtest(spread_df["spread_10y_3m_bp"],
                              wide["10 Yr"], wide["3 Mo"])
        if res:
            st.line_chart(res["curves"] * 100)
            st.dataframe(res["stats"], use_container_width=True)
            st.caption(f"Time in cash: {res['time_in_cash_pct']}% of "
                       f"{res['n_days']} trading days")
    except (SourceUnavailable, KeyError) as exc:
        st.warning(f"Backtest unavailable: {exc}")

with tab_hist:
    hist = history.load_metric("stress_index", CFG["history"]["db_path"])
    if hist.empty:
        st.info("No run history recorded yet — every `run_monitor.py` run "
                "appends a snapshot to DuckDB; come back after a few runs.")
    else:
        wide = hist.pivot_table(index="run_ts", columns="entity",
                                values="value")
        st.line_chart(wide)
