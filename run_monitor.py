from __future__ import annotations

import argparse
import traceback

import pandas as pd

from src.config import load_config
from src.logging_setup import setup_logging
from src.clients.base import SourceUnavailable
from src.clients.ustreasury import USTreasuryClient
from src.clients.ecb import ECBClient
from src.clients.worldbank import WorldBankClient
from src.clients.bankofengland import BankOfEnglandClient
from src.clients.imf import IMFClient
from src.clients.eurostat import EurostatClient
from src.clients.bis import BISClient
from src.clients.oecd import OECDClient
from src.clients.nbu import NBUClient
from src.clients.fred import FREDClient
from src.analytics import yield_curve as yc
from src.analytics.fx import fx_metrics, fx_timeseries
from src.analytics.scorecard import scorecard
from src.analytics import events, nowcast, correlations, backtest as bt
from src.analytics.real_fx import real_fx_index, real_fx_summary
from src.analytics.debt import debt_panel
from src import report, history, alerts

CFG = load_config()
log = setup_logging()



def section_treasury(args, sections, ctx):
    client = USTreasuryClient()
    curve = client.yield_curve(years=CFG["treasury_years"], refresh=args.refresh)
    spread_df = yc.spreads(curve)
    min_days = CFG["analytics"]["inversion_min_days"]
    episodes_3m = yc.inversion_episodes(
        spread_df.get("spread_10y_3m_bp", pd.Series(dtype=float)), min_days)
    episodes_2y = yc.inversion_episodes(
        spread_df.get("spread_10y_2y_bp", pd.Series(dtype=float)), min_days)
    snaps = yc.latest_curve_snapshots(curve)
    chart = report.chart_yield_curve(snaps, spread_df, episodes_3m)
    ctx.update({"curve": curve, "spread_df": spread_df,
                "episodes_3m": episodes_3m})

    latest = spread_df.dropna().iloc[-1]
    lines = [
        "## US Treasury yield curve",
        f"*Source: U.S. Department of the Treasury — daily par yield curve "
        f"({curve['date'].min().date()} → {curve['date'].max().date()}, "
        f"{spread_df.shape[0]} trading days)*",
        "",
        f"![Yield curve]({chart.name})",
        "",
        f"![Curve surface]({report.chart_curve_heatmap(curve).name})",
        "",
        f"- Latest 10Y−3M spread: **{latest.get('spread_10y_3m_bp', float('nan')):.0f} bp**",
        f"- Latest 10Y−2Y spread: **{latest.get('spread_10y_2y_bp', float('nan')):.0f} bp**",
        "",
    ]
    for name, eps in [("10Y−3M", episodes_3m), ("10Y−2Y", episodes_2y)]:
        if not eps.empty:
            lines += [f"**Inversion episodes detected ({name}):**", "",
                      eps.to_markdown(index=False), ""]
    sections.extend(lines)
    log.info("  + US Treasury: %s days, %s inversion episode(s) on 10Y-3M",
             spread_df.shape[0], len(episodes_3m))


def section_ecb(args, sections, ctx):
    client = ECBClient()
    fx = client.fx_daily(CFG["fx_currencies"], start=CFG["fx_start"],
                         refresh=args.refresh)
    metrics = fx_metrics(fx, vol_window=CFG["analytics"]["fx_vol_window"])
    ts = fx_timeseries(fx, vol_window=CFG["analytics"]["fx_vol_window"])
    chart = report.chart_fx(ts)
    ctx.update({"fx": fx, "fx_ts": ts, "fx_metrics": metrics})
    dfr_line = "- ECB deposit facility rate: unavailable this run"
    try:
        dfr = client.deposit_facility_rate(start=CFG["fx_start"],
                                           refresh=args.refresh)
        ctx["dfr"] = dfr
        dfr_line = (f"- ECB deposit facility rate (latest): "
                    f"**{dfr['rate_pct'].iloc[-1]:.2f}%** "
                    f"as of {dfr['date'].iloc[-1].date()}")
    except Exception:                                       
        pass
    sections.extend([
        "## FX & ECB policy",
        "*Source: European Central Bank Data Portal — daily euro reference rates*",
        "",
        f"![FX monitor]({chart.name})", "",
        f"![FX drawdowns]({report.chart_fx_drawdown(ts).name})", "",
        metrics.to_markdown(index=False), "", dfr_line, "",
    ])
    log.info("  + ECB: %s FX observations across %s pairs",
             len(fx), fx["currency"].nunique())


def section_worldbank(args, sections, ctx):
    client = WorldBankClient()
    indicators = {code: tuple(v) for code, v in CFG["wb_indicators"].items()}
    wb = client.all_indicators(CFG["countries"], date_range=CFG["wb_range"],
                               refresh=args.refresh, indicators=indicators)
    signs = {short: sign for short, sign in indicators.values()}
    sc = scorecard(wb, stress_signs={k: v for k, v in signs.items() if v})
    chart = report.chart_scorecard(sc)
    ctx.update({"wb": wb, "scorecard": sc})
    show_cols = [c for c in ["country", "gdp_growth_pct", "inflation_pct",
                             "unemployment_pct", "govt_debt_gdp_pct",
                             "stress_index"] if c in sc.columns]
    sections.extend([
        "## Cross-country macro scorecard",
        "*Source: World Bank — World Development Indicators "
        f"({CFG['wb_range']}); z-scores vs each country's own history*",
        "",
        f"![Macro stress]({chart.name})", "",
        sc[show_cols].to_markdown(index=False), "",
    ])
    log.info("  + World Bank: %s observations, %s countries scored",
             len(wb), sc.shape[0])


def section_boe(args, sections, ctx):
    client = BankOfEnglandClient()
    rate = client.bank_rate(date_from=CFG["boe_date_from"],
                            refresh=args.refresh)
    ctx["boe_rate"] = rate
    pol_chart = report.chart_policy_rates(ctx.get("dfr"), rate)
    sections.extend([
        "## UK policy rate (experimental source)",
        "*Source: Bank of England IADB — Official Bank Rate (IUDBEDR)*", "",
        f"![Policy rates]({pol_chart.name})", "",
        f"- Latest Bank Rate: **{rate['rate_pct'].iloc[-1]:.2f}%** "
        f"as of {rate['date'].iloc[-1].date()} "
        f"({len(rate)} observations since {rate['date'].iloc[0].date()})", "",
    ])
    log.info("  + Bank of England: %s observations", len(rate))


def section_imf(args, sections, ctx):
    client = IMFClient()
    cpi = client.cpi_monthly(CFG["countries"], refresh=args.refresh)
    ctx["imf_cpi"] = cpi
    yoy = []
    for geo, grp in cpi.groupby("geo"):
        grp = grp.sort_values("date")
        if len(grp) > 12:
            yoy.append({"geo": geo,
                        "cpi_yoy_pct": round(float(
                            grp["value"].iloc[-1] / grp["value"].iloc[-13]
                            * 100 - 100), 1),
                        "as_of": grp["date"].iloc[-1].date()})
    sections.extend([
        "## IMF monthly CPI (second SDMX provider)",
        "*Source: IMF Data (data.imf.org), CPI dataset — monthly headline "
        "CPI index*",
        "",
        pd.DataFrame(yoy).to_markdown(index=False) if yoy
        else "_insufficient history for YoY_", "",
    ])
    log.info("  + IMF: %s CPI observations", len(cpi))


def section_eurostat(args, sections, ctx):
    client = EurostatClient()
    hicp = client.hicp_annual_rate(CFG["countries"],
                                   periods=CFG["eurostat_periods"],
                                   refresh=args.refresh)
    ctx["hicp"] = hicp
    latest = (hicp.sort_values("date").groupby("geo").tail(1)
                  .rename(columns={"value": "hicp_yoy_pct"}))
    latest["as_of"] = latest["date"].dt.date
    sections.extend([
        "## Eurostat monthly HICP — European inflation at monthly resolution",
        "*Source: Eurostat dissemination API — HICP annual rate of change. "
        "Upgrades European countries from World Bank annual to monthly data.*",
        "",
        f"![HICP]({report.chart_geo_lines(hicp, 'Eurostat HICP — annual inflation rate, monthly', 'HICP, % YoY', 'eurostat_hicp.png', hline=2.0, hline_label='2% target').name})", "",
        latest[["geo", "hicp_yoy_pct", "as_of"]].to_markdown(index=False), "",
    ])
    log.info("  + Eurostat: %s HICP observations", len(hicp))


def section_bis(args, sections, ctx):
    client = BISClient()
    gap = client.credit_gap(CFG["countries"], refresh=args.refresh)
    ctx["credit_gap"] = gap
    latest = gap.sort_values("date").groupby("geo").tail(1)
    latest = latest.rename(columns={"value": "credit_gap_pp"})
    latest["as_of"] = latest["date"].dt.date
    sections.extend([
        "## BIS credit-to-GDP gap (experimental source)",
        "*Source: BIS — the Bank for International Settlements' own "
        "early-warning indicator for banking stress (gap vs long-term trend, "
        "percentage points). Readings above ~9pp historically preceded "
        "crises.*", "",
        f"![Credit gap]({report.chart_geo_lines(gap, 'BIS credit-to-GDP gap — early-warning indicator', 'gap, pp', 'bis_credit_gap.png', hline=9.0, hline_label='BIS warning threshold (+9pp)').name})", "",
        latest[["geo", "credit_gap_pp", "as_of"]].to_markdown(index=False), "",
    ])
    log.info("  + BIS: %s credit-gap observations", len(gap))


def section_oecd(args, sections, ctx):
    client = OECDClient()
    cli = client.cli(CFG["countries"], refresh=args.refresh)
    ctx["cli"] = cli
    latest = cli.sort_values("date").groupby("geo").tail(1)
    latest = latest.rename(columns={"value": "cli"})
    latest["signal"] = latest["cli"].apply(
        lambda v: "above trend" if v > 100 else "below trend")
    latest["as_of"] = latest["date"].dt.date
    sections.extend([
        "## OECD Composite Leading Indicator (experimental source)",
        "*Source: OECD — amplitude-adjusted CLI, 100 = long-term trend. An "
        "independent 'is this economy turning?' cross-check on the "
        "scorecard.*", "",
        f"![CLI]({report.chart_geo_lines(cli, 'OECD Composite Leading Indicator (100 = trend)', 'CLI', 'oecd_cli.png', hline=100.0, hline_label='long-term trend').name})", "",
        latest[["geo", "cli", "signal", "as_of"]].to_markdown(index=False), "",
    ])
    log.info("  + OECD: %s CLI observations", len(cli))


def section_nbu(args, sections, ctx):
    client = NBUClient()
    uah = client.uah_rate(refresh=args.refresh)
    ctx["uah"] = uah
    lines = [
        "## National Bank of Ukraine",
        "*Source: NBU open data API — official UAH/USD rate. The one "
        "economy in the panel under acute stress, so it anchors the "
        "high end of the stress-index scale.*", "",
        f"- Latest official UAH/USD: **{uah['rate'].iloc[-1]:.2f}** "
        f"as of {uah['date'].iloc[-1].date()} "
        f"({len(uah)} observations since {uah['date'].iloc[0].date()})",
    ]
    m3 = None
    try:
        mon = client.monetary_aggregates(refresh=args.refresh)
        m3 = mon[mon["aggregate"] == "M3"].sort_values("date")
        if len(m3) > 12:
            yoy = (m3["value"].iloc[-1] / m3["value"].iloc[-13] - 1) * 100
            lines.append(f"- Money supply M3: **{yoy:+.1f}% YoY** "
                         f"as of {m3['date'].iloc[-1].date()}")
    except Exception:
        lines.append("- NBU monetary aggregates: unavailable this run")
    lines += ["", f"![Ukraine]({report.chart_nbu(uah, m3).name})"]
    sections.extend(lines + [""])
    log.info("  + NBU: %s UAH observations", len(uah))


def section_fred(args, sections, ctx):
    client = FREDClient(api_key_env=CFG["fred"]["api_key_env"])
    series_ids = CFG["fred"]["series"]
    if not series_ids:
        raise SourceUnavailable("fred: no series configured")
    df = client.many(series_ids, refresh=args.refresh)
    ctx["fred"] = df
    latest = df.sort_values("date").groupby("series").tail(1)
    latest["as_of"] = latest["date"].dt.date
    sections.extend([
        "## FRED — US high-frequency panel (optional, key required)",
        "*Source: Federal Reserve Bank of St. Louis. The only key-required "
        "source; skipped entirely unless FRED_API_KEY is set.*", "",
        latest[["series", "value", "as_of"]].to_markdown(index=False), "",
    ])
    log.info("  + FRED: %s observations across %s series",
             len(df), df["series"].nunique())




def section_event_study(args, sections, ctx):
    window = CFG["analytics"]["event_window_days"]
    parts = []
    if "spread_df" in ctx and "spread_10y_3m_bp" in ctx["spread_df"]:
        parts.append(events.curve_event_study(
            ctx["spread_df"]["spread_10y_3m_bp"], window))
    if "fx_ts" in ctx:
        parts.append(events.fx_event_study(ctx["fx_ts"], window=window))
    parts = [p for p in parts if not p.empty]
    if not parts:
        raise SourceUnavailable("event study: no base series this run")
    table = pd.concat(parts, ignore_index=True)
    lines = [
        "## Event study — policy decisions vs market moves",
        f"*Move measured from {window} trading days before to {window} after "
        "each FOMC/ECB decision (hardcoded official calendar — see ADR-0006). "
        "Curve moves in bp; FX in index points (start=100).*", "",
        table.to_markdown(index=False), "",
    ]
    last_event = max(pd.to_datetime(events.FOMC_DATES + events.ECB_DATES))
    if "spread_df" in ctx and ctx["spread_df"].index.max() > last_event:
        lines += ["> **Note:** the data now extends past the last date in "
                  "the hardcoded FOMC/ECB calendar — add the next year's "
                  "meeting dates in `src/analytics/events.py`.", ""]
    sections.extend(lines)
    log.info("  + Event study: %s events measured", len(table))


def section_nowcast(args, sections, ctx):
    horizon = CFG["analytics"]["nowcast_horizon_days"]
    lines = ["## Nowcast (illustrative)", ""]
    produced = False
    if "spread_df" in ctx and "spread_10y_3m_bp" in ctx["spread_df"]:
        res = nowcast.holt_forecast(ctx["spread_df"]["spread_10y_3m_bp"],
                                    horizon=horizon)
        got = nowcast.nowcast_lines(res, "10Y-3M spread", "bp")
        if got:
            lines += got
            produced = True
    if "fx_ts" in ctx:
        usd = ctx["fx_ts"][ctx["fx_ts"]["currency"] == "USD"]
        if len(usd):
            res = nowcast.holt_forecast(
                usd.set_index("date")["rate"], horizon=horizon)
            got = nowcast.nowcast_lines(res, "EUR/USD", "")
            if got:
                lines += got
                produced = True
    if not produced:
        raise SourceUnavailable("nowcast: no base series this run")
    sections.extend(lines)
    log.info("  + Nowcast: produced")


def section_correlations(args, sections, ctx):
    named = {}
    if "spread_df" in ctx:
        for col in ctx["spread_df"].columns:
            named[col.replace("spread_", "").replace("_bp", "")] = \
                ctx["spread_df"][col]
    if "fx_ts" in ctx:
        for ccy, grp in ctx["fx_ts"].groupby("currency"):
            named[f"EUR/{ccy}"] = grp.set_index("date")["rate"]
            named[f"EUR/{ccy} vol"] = grp.set_index("date")["roll_vol_pct"]
    if "boe_rate" in ctx:
        named["UK bank rate"] = ctx["boe_rate"].set_index("date")["rate_pct"]
    corr = correlations.correlation_matrix(named)
    if corr.empty:
        raise SourceUnavailable("correlations: <2 overlapping series")
    chart = report.chart_correlations(corr)
    top = correlations.strongest_pairs(corr)
    roll_lines = []
    if "spread_df" in ctx and "fx_ts" in ctx:
        usd = ctx["fx_ts"][ctx["fx_ts"]["currency"] == "USD"]
        if len(usd) and "spread_10y_3m_bp" in ctx["spread_df"]:
            rc = report.chart_rolling_corr(
                ctx["spread_df"]["spread_10y_3m_bp"],
                usd.set_index("date")["rate"],
                "10Y-3M spread", "EUR/USD")
            if rc:
                roll_lines = [f"![Rolling correlation]({rc.name})", ""]
    sections.extend([
        "## Cross-indicator correlations",
        "*Pearson correlation of daily changes on overlapping dates "
        "(levels of trending series would give spurious correlations).*", "",
        f"![Correlations]({chart.name})", "",
        "**Strongest co-movements:**", "", top.to_markdown(index=False), "",
    ] + roll_lines)
    log.info("  + Correlations: %sx%s matrix", *corr.shape)


def section_backtest(args, sections, ctx):
    if "curve" not in ctx or "spread_df" not in ctx:
        raise SourceUnavailable("backtest: needs Treasury data")
    wide = yc.to_wide(ctx["curve"])
    if not {"10 Yr", "3 Mo"}.issubset(wide.columns):
        raise SourceUnavailable("backtest: 10Y/3M tenors missing")
    res = bt.run_backtest(ctx["spread_df"]["spread_10y_3m_bp"],
                          wide["10 Yr"], wide["3 Mo"],
                          duration=CFG["analytics"]["backtest_duration_years"])
    if not res:
        raise SourceUnavailable("backtest: not enough overlapping data")
    chart = report.chart_backtest(res["curves"], res["drawdown"])
    sections.extend([
        "## Toy signal backtest (illustrative — read the caveats)",
        "*Strategy: hold a simulated constant-maturity 10Y note; switch to "
        "3M-bill carry while the 10Y-3M spread is inverted. Signal lagged "
        "one day. Bond returns are a duration approximation (r = carry - "
        "D*dy) with no convexity, costs, or taxes. This demonstrates the "
        "tear-sheet workflow, not an investable strategy (see ADR-0007).*",
        "",
        f"![Backtest]({chart.name})", "",
        res["stats"].to_markdown(), "",
        f"- Sample: {res['n_days']} trading days; time in cash: "
        f"**{res['time_in_cash_pct']}%**", "",
    ])
    log.info("  + Backtest: %s days simulated", res["n_days"])


def section_real_fx(args, sections, ctx):
    if "fx" not in ctx or "wb" not in ctx:
        raise SourceUnavailable("real FX: needs both ECB FX and World Bank CPI")
    rfx = real_fx_index(ctx["fx"], ctx["wb"])
    if rfx.empty:
        raise SourceUnavailable("real FX: no overlapping CPI/FX coverage")
    chart = report.chart_real_fx(rfx)
    summary = real_fx_summary(rfx)
    sections.extend([
        "## Real (PPP-adjusted) exchange rates",
        "*ECB nominal rates deflated by relative CPI (World Bank), Germany "
        "as euro-area proxy. The gap between nominal and real change is "
        "the two economies' inflation differential.*", "",
        f"![Real FX]({chart.name})", "",
        summary.to_markdown(index=False), "",
    ])
    log.info("  + Real FX: %s currencies", summary.shape[0])


def section_debt(args, sections, ctx):
    if "wb" not in ctx:
        raise SourceUnavailable("debt panel: needs World Bank data")
    panel = debt_panel(ctx["wb"])
    if panel.empty:
        raise SourceUnavailable(
            "debt panel: debt/real-rate indicators not in cache yet "
            "(populate with --refresh)")
    show = [c for c in ["country", "govt_debt_gdp_pct", "gdp_growth_pct",
                        "real_interest_pct", "r_minus_g_pp", "verdict"]
            if c in panel.columns]
    sections.extend([
        "## Debt sustainability — the r vs g check",
        "*World Bank data. Screening heuristic only: no primary-balance "
        "path or maturity structure. r > g with high debt = the ratio "
        "snowballs without surpluses.*", "",
        panel[show].to_markdown(index=False), "",
    ])
    log.info("  + Debt panel: %s countries", panel.shape[0])


def section_history(args, sections, ctx):
    if not CFG["history"]["enabled"]:
        raise SourceUnavailable("history disabled in config")
    db = CFG["history"]["db_path"]
    metrics = []
    if "spread_df" in ctx:
        last = ctx["spread_df"].dropna()
        for col in last.columns:
            metrics.append({"metric": col, "entity": "US",
                            "as_of": last.index[-1].date(),
                            "value": float(last[col].iloc[-1])})
    if "scorecard" in ctx:
        for _, row in ctx["scorecard"].iterrows():
            if row.get("stress_index") is not None:
                metrics.append({"metric": "stress_index",
                                "entity": row["country_iso3"],
                                "as_of": pd.Timestamp.today().date(),
                                "value": float(row["stress_index"])})
    if "fx_metrics" in ctx:
        for _, row in ctx["fx_metrics"].iterrows():
            if row["ann_vol_30d_pct"] is not None:
                metrics.append({"metric": "fx_vol_30d",
                                "entity": f"EUR/{row['currency']}",
                                "as_of": row["last"],
                                "value": float(row["ann_vol_30d_pct"])})
    n = history.record_run(metrics, db)
    runs = history.run_count(db)
    lines = ["## Run history (DuckDB)",
             f"*{n} metrics appended this run; {runs} runs recorded in "
             f"`{db}`. Each refresh appends a dated snapshot rather than "
             "overwriting the last one.*", ""]
    hist = history.load_metric("stress_index", db)
    if not hist.empty and hist["run_ts"].nunique() > 1:
        chart = report.chart_stress_history(hist)
        lines += [f"![Stress history]({chart.name})", ""]
    sections.extend(lines)
    log.info("  + History: %s metrics appended (%s runs total)", n, runs)


def section_alerts(args, sections, ctx):
    msgs = alerts.compose_alerts(
        ctx.get("episodes_3m"),
        ctx["spread_df"].index[-1] if "spread_df" in ctx else None,
        ctx.get("scorecard"),
        stress_threshold=CFG["thresholds"]["stress_alert"])
    sent = alerts.send_alerts(msgs, CFG.get("alerts", {}))
    if msgs:
        sections.extend(["## Alerts", ""]
                        + [f"- {m}" for m in msgs]
                        + ["", f"*Delivered to {sent} webhook(s); configure "
                           "Slack/Telegram via env vars in config.yaml.*", ""])
    log.info("  + Alerts: %s composed, %s sent", len(msgs), sent)


SECTIONS = [
    ("US Treasury", section_treasury),
    ("ECB", section_ecb),
    ("World Bank", section_worldbank),
    ("Bank of England", section_boe),
    ("IMF", section_imf),
    ("Eurostat", section_eurostat),
    ("BIS", section_bis),
    ("OECD", section_oecd),
    ("NBU", section_nbu),
    ("FRED", section_fred),
    ("Event study", section_event_study),
    ("Nowcast", section_nowcast),
    ("Correlations", section_correlations),
    ("Backtest", section_backtest),
    ("Real FX", section_real_fx),
    ("Debt panel", section_debt),
    ("History", section_history),
    ("Alerts", section_alerts),
]


def main():
    parser = argparse.ArgumentParser(description="Macro Pulse monitor")
    parser.add_argument("--refresh", action="store_true",
                        help="force live API pulls (default: cache if present)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    global log
    log = setup_logging(verbose=args.verbose)

    log.info("Macro Pulse — building report (10 sources + %s derived sections)",
             len(SECTIONS) - 10)
    sections = []
    ctx = {}
    ok, skipped = 0, []
    for name, fn in SECTIONS:
        try:
            fn(args, sections, ctx)
            ok += 1
        except (SourceUnavailable, Exception) as exc:       
            skipped.append(name)
            log.info("  - %s: skipped — %s", name, exc)
            if args.refresh and not isinstance(exc, SourceUnavailable):
                traceback.print_exc(limit=1)

    if skipped:
        sections += ["---",
                     f"*Sections skipped this run (source or prerequisite "
                     f"unavailable): {', '.join(skipped)}. Re-run with "
                     f"`--refresh` when online.*"]

    path = report.write_report(sections)
    log.info("Done: %s/%s sections built -> %s", ok, len(SECTIONS), path)


if __name__ == "__main__":
    main()
