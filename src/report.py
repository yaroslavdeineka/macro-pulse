from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BLUE = "#2563EB"
LIGHT = "#93C5FD"
RED = "#DC2626"

OUT_DIR = Path(__file__).resolve().parents[1] / "outputs"


def chart_yield_curve(snapshots: pd.DataFrame, spread_df: pd.DataFrame,
                      episodes: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Left: curve shape at up to three snapshots
    colors = [BLUE, LIGHT, "#CBD5E1"]
    for i, (label, grp) in enumerate(snapshots.groupby("snapshot", sort=False)):
        axes[0].plot(grp["maturity_years"], grp["yield_pct"],
                     marker="o", ms=3, lw=1.8,
                     color=colors[i % len(colors)], label=label)
    axes[0].set_xscale("log")
    axes[0].set_xticks([0.25, 1, 2, 5, 10, 30])
    axes[0].set_xticklabels(["3M", "1Y", "2Y", "5Y", "10Y", "30Y"])
    axes[0].set_xlabel("Maturity")
    axes[0].set_ylabel("Par yield, %")
    axes[0].set_title("US Treasury par yield curve")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)

    # Right: 10Y-3M spread with inversion shading
    if "spread_10y_3m_bp" in spread_df:
        s = spread_df["spread_10y_3m_bp"]
        axes[1].plot(s.index, s, color=BLUE, lw=1.5, label="10Y − 3M")
    if "spread_10y_2y_bp" in spread_df:
        s2 = spread_df["spread_10y_2y_bp"]
        axes[1].plot(s2.index, s2, color=LIGHT, lw=1.5, label="10Y − 2Y")
    axes[1].axhline(0, color=RED, lw=1, ls="--")
    axes[1].fill_between(spread_df.index, spread_df.min(axis=1), 0,
                         where=spread_df.min(axis=1) < 0,
                         color=RED, alpha=0.12, label="inverted")
    axes[1].set_ylabel("Spread, bp")
    axes[1].set_title("Curve spreads & inversion episodes")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    fig.suptitle("Macro Pulse · US yield curve monitor", fontweight="bold")
    fig.tight_layout()
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / "yield_curve.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_fx(fx_ts: pd.DataFrame) -> Path:
    ccys = fx_ts["currency"].unique()
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    palette = [BLUE, "#F59E0B", "#10B981", "#8B5CF6"]
    for i, ccy in enumerate(ccys):
        grp = fx_ts[fx_ts["currency"] == ccy]
        # normalise levels to 100 at start so pairs share an axis
        base = grp["rate"].iloc[0]
        axes[0].plot(grp["date"], grp["rate"] / base * 100,
                     lw=1.5, color=palette[i % 4], label=f"EUR/{ccy}")
        axes[1].plot(grp["date"], grp["roll_vol_pct"],
                     lw=1.3, color=palette[i % 4], label=f"EUR/{ccy}")
    axes[0].set_ylabel("Level (start = 100)")
    axes[0].set_title("ECB euro reference rates")
    axes[1].set_ylabel("30d ann. vol, %")
    for ax in axes:
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / "fx_monitor.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_scorecard(sc: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    colors = [RED if v > 0 else "#10B981" for v in sc["stress_index"]]
    ax.barh(sc["country"], sc["stress_index"], color=colors, alpha=0.85)
    ax.axvline(0, color="#333", lw=1)
    ax.invert_yaxis()
    ax.set_xlabel("Composite stress index (z-scores vs own history)")
    ax.set_title("Macro Stress Index — latest observation vs each country's history")
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    path = OUT_DIR / "macro_stress.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def write_report(sections: list[str]) -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / "macro_report.md"
    header = ["# Macro Pulse — monitor report", ""]
    path.write_text("\n".join(header + sections), encoding="utf-8")
    return path


def chart_backtest(curves: pd.DataFrame, drawdown: pd.Series) -> Path:
    """Equity curves + underwater plot — the quantstats-style tear sheet."""
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                             gridspec_kw={"height_ratios": [2.2, 1]})
    palette = {"strategy": BLUE, "buy_and_hold_10y": "#F59E0B",
               "cash": "#94A3B8"}
    for col in curves.columns:
        axes[0].plot(curves.index, curves[col] * 100, lw=1.6,
                     color=palette.get(col, LIGHT), label=col.replace("_", " "))
    axes[0].set_ylabel("Growth of 100 (simulated)")
    axes[0].set_title("Curve-signal strategy vs benchmarks — illustrative "
                      "(simulated bond returns, no costs)")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)
    axes[1].fill_between(drawdown.index, drawdown * 100, 0,
                         color=RED, alpha=0.35)
    axes[1].set_ylabel("Strategy drawdown, %")
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / "backtest.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_correlations(corr: pd.DataFrame) -> Path:
    """Readable heatmap of the cross-indicator correlation matrix.

    Design choices for LARGE matrices (20+ series):
      * the trivial diagonal (always 1.0) is masked out, and the color
        scale stretches to the strongest OFF-diagonal value — otherwise
        every real correlation drowns in near-white;
      * numbers are printed only where |r| >= 0.20 (and only if the
        matrix is small enough for the text to fit) — weak cells stay
        blank instead of becoming visual noise;
      * figure size grows with the matrix; soft diverging palette with
        white cell borders instead of a saturated red/blue wall.
    """
    import numpy as np
    n = len(corr.columns)
    vals = corr.values.astype(float).copy()
    np.fill_diagonal(vals, np.nan)                 # mask trivial 1.0s
    vmax = np.nanmax(np.abs(vals))
    vmax = max(0.2, float(np.ceil(vmax * 10) / 10))
    side = max(7.5, 0.42 * n + 2.5)
    fig, ax = plt.subplots(figsize=(side * 1.15, side))
    masked = np.ma.masked_invalid(vals)
    cmap = plt.get_cmap("coolwarm").copy()
    cmap.set_bad("#E8E8E8")                        # diagonal = neutral grey
    im = ax.pcolormesh(masked, vmin=-vmax, vmax=vmax, cmap=cmap,
                       edgecolors="white", linewidth=1.2)
    ax.invert_yaxis()
    ax.set_xticks([i + 0.5 for i in range(n)])
    ax.set_xticklabels(corr.columns, rotation=60, ha="right", fontsize=9)
    ax.set_yticks([i + 0.5 for i in range(n)])
    ax.set_yticklabels(corr.index, fontsize=9)
    annotate = n <= 26
    if annotate:
        for i in range(n):
            for j in range(n):
                v = vals[i, j]
                if np.isnan(v) or abs(v) < 0.20:
                    continue                       # blank out the noise
                ax.text(j + 0.5, i + 0.5, f"{v:+.2f}".replace("0.", "."),
                        ha="center", va="center", fontsize=8,
                        fontweight="bold",
                        color="white" if abs(v) > 0.6 * vmax else "#1a1a1a")
    ax.set_title("Cross-indicator correlations (daily changes) — "
                 f"labels shown where |r| ≥ 0.20; color scale ±{vmax:.1f}",
                 fontsize=11)
    cb = fig.colorbar(im, ax=ax, shrink=0.7)
    cb.set_label("Pearson r", fontsize=9)
    fig.tight_layout()
    path = OUT_DIR / "correlations.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_real_fx(rfx: pd.DataFrame) -> Path:
    """Nominal vs real exchange-rate indices per currency."""
    ccys = list(rfx["currency"].unique())
    n = len(ccys)
    fig, axes = plt.subplots(n, 1, figsize=(10, 2.6 * n), sharex=True,
                             squeeze=False)
    for i, ccy in enumerate(ccys):
        ax = axes[i][0]
        g = rfx[rfx["currency"] == ccy].sort_values("date")
        ax.plot(g["date"], g["nominal_idx"], lw=1.4, color=LIGHT,
                label="nominal")
        ax.plot(g["date"], g["real_idx"], lw=1.6, color=BLUE,
                label="real (CPI-adjusted)")
        ax.axhline(100, color="#999", lw=0.8, ls=":")
        ax.set_ylabel(f"EUR/{ccy} (start=100)")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    axes[0][0].set_title("Real vs nominal exchange rates — PPP view")
    fig.tight_layout()
    path = OUT_DIR / "real_fx.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_stress_history(hist: pd.DataFrame) -> Path:
    """Stress-index evolution across recorded runs (DuckDB history)."""
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for entity, grp in hist.groupby("entity"):
        ax.plot(grp["run_ts"], grp["value"], marker="o", ms=3,
                lw=1.3, label=entity)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_ylabel("Stress index")
    ax.set_title("Macro Stress Index — evolution across runs")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / "stress_history.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_curve_heatmap(curve: pd.DataFrame) -> Path:
    """Full yield-curve surface as a date x maturity heatmap, plus one
    year-end curve snapshot per year."""
    import numpy as np
    wide = curve.pivot_table(index="date", columns="maturity_years",
                             values="yield_pct").sort_index()
    # drop tenors that don't span the sample (e.g. 4 Mo exists only from
    # 2022-10) — partial rows render as white stripes in the heatmap
    wide = wide.loc[:, wide.notna().mean() > 0.9]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5),
                             gridspec_kw={"width_ratios": [1.6, 1]})
    mesh = axes[0].pcolormesh(wide.index, wide.columns, wide.T.values,
                              cmap="RdYlBu_r", shading="nearest")
    axes[0].set_yscale("log")
    axes[0].set_ylim(float(wide.columns.min()), float(wide.columns.max()))
    axes[0].set_yticks([0.25, 1, 2, 5, 10, 30])
    axes[0].set_yticklabels(["3M", "1Y", "2Y", "5Y", "10Y", "30Y"])
    axes[0].set_title("Yield-curve surface (color = par yield, %)")
    fig.colorbar(mesh, ax=axes[0], shrink=0.85)

    years = sorted(curve["date"].dt.year.unique())
    cmap = plt.get_cmap("viridis")
    for i, yr in enumerate(years):
        sub = curve[curve["date"].dt.year == yr]
        last = sub[sub["date"] == sub["date"].max()]
        last = last.sort_values("maturity_years")
        axes[1].plot(last["maturity_years"], last["yield_pct"],
                     color=cmap(i / max(len(years) - 1, 1)), lw=1.6,
                     label=str(yr))
    axes[1].set_xscale("log")
    axes[1].set_xticks([0.25, 1, 2, 5, 10, 30])
    axes[1].set_xticklabels(["3M", "1Y", "2Y", "5Y", "10Y", "30Y"])
    axes[1].set_title("Year-end curve, one line per year")
    axes[1].legend(fontsize=7, ncol=2)
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / "curve_heatmap.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_policy_rates(dfr: pd.DataFrame | None,
                       boe: pd.DataFrame | None) -> Path:
    """ECB deposit facility rate vs Bank of England Bank Rate — the two
    policy cycles side by side (step lines)."""
    fig, ax = plt.subplots(figsize=(11, 4.5))
    if dfr is not None and len(dfr):
        ax.step(dfr["date"], dfr["rate_pct"], where="post", lw=1.8,
                color=BLUE, label="ECB deposit facility rate")
    if boe is not None and len(boe):
        ax.step(boe["date"], boe["rate_pct"], where="post", lw=1.8,
                color="#F59E0B", label="BoE Bank Rate")
    ax.axhline(0, color="#999", lw=0.8, ls=":")
    ax.set_ylabel("%")
    ax.set_title("Policy rates — two central-bank cycles")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / "policy_rates.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_geo_lines(df: pd.DataFrame, title: str, ylabel: str,
                    fname: str, hline: float | None = None,
                    hline_label: str = "") -> Path:
    """Generic per-country line chart for monthly/quarterly indicators
    (Eurostat HICP, BIS credit gap, OECD CLI)."""
    fig, ax = plt.subplots(figsize=(11, 4.8))
    palette = [BLUE, "#F59E0B", "#10B981", "#8B5CF6", RED,
               "#0EA5E9", "#F472B6", "#84CC16", "#64748B", "#EAB308"]
    for i, (geo, grp) in enumerate(df.groupby("geo")):
        grp = grp.sort_values("date")
        ax.plot(grp["date"], grp["value"], lw=1.4,
                color=palette[i % len(palette)], label=geo)
    if hline is not None:
        ax.axhline(hline, color=RED, lw=1.2, ls="--", label=hline_label)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / fname
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_nbu(uah: pd.DataFrame, m3: pd.DataFrame | None) -> Path:
    """UAH/USD official rate + money-supply growth — a decade including
    the 2022 full-scale-invasion shock, visible in both panels."""
    n = 2 if m3 is not None and len(m3) > 13 else 1
    fig, axes = plt.subplots(n, 1, figsize=(11, 3.2 * n), sharex=True,
                             squeeze=False)
    ax = axes[0][0]
    ax.plot(uah["date"], uah["rate"], lw=1.5, color=BLUE)
    war = pd.Timestamp("2022-02-24")
    if uah["date"].min() < war < uah["date"].max():
        ax.axvline(war, color=RED, lw=1.2, ls="--")
        ax.annotate("full-scale invasion", xy=(war, uah["rate"].max()),
                    fontsize=8, color=RED, ha="left")
    ax.set_ylabel("UAH per USD")
    ax.set_title("NBU official UAH/USD rate")
    ax.grid(alpha=0.3)
    if n == 2:
        m3 = m3.sort_values("date")
        yoy = (m3.set_index("date")["value"].pct_change(12) * 100).dropna()
        ax2 = axes[1][0]
        ax2.plot(yoy.index, yoy.values, lw=1.5, color="#F59E0B")
        ax2.axhline(0, color="#999", lw=0.8)
        ax2.set_ylabel("M3, % YoY")
        ax2.set_title("Money supply growth")
        ax2.grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / "nbu_ukraine.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_fx_drawdown(fx_ts: pd.DataFrame, top_n: int = 5) -> Path:
    """Underwater plot per currency vs EUR — which currencies are how far
    below their period peak right now."""
    fig, ax = plt.subplots(figsize=(11, 4.5))
    palette = [BLUE, "#F59E0B", "#10B981", "#8B5CF6", RED]
    # rank by depth of current drawdown
    depth = {}
    for ccy, grp in fx_ts.groupby("currency"):
        s = grp.set_index("date")["rate"].sort_index()
        dd = (s / s.cummax() - 1) * 100
        depth[ccy] = dd.iloc[-1]
    worst = sorted(depth, key=depth.get)[:top_n]
    for i, ccy in enumerate(worst):
        grp = fx_ts[fx_ts["currency"] == ccy]
        s = grp.set_index("date")["rate"].sort_index()
        dd = (s / s.cummax() - 1) * 100
        ax.plot(dd.index, dd.values, lw=1.2,
                color=palette[i % len(palette)],
                label=f"EUR/{ccy} (now {depth[ccy]:.1f}%)")
        ax.fill_between(dd.index, dd.values, 0, alpha=0.06,
                        color=palette[i % len(palette)])
    ax.set_ylabel("Drawdown from period peak, %")
    ax.set_title(f"FX underwater plot — {top_n} deepest current drawdowns vs EUR")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / "fx_drawdown.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_rolling_corr(a: pd.Series, b: pd.Series, label_a: str,
                       label_b: str, window: int = 90) -> Path | None:
    """Rolling correlation of daily changes between two series, to show
    how the relationship shifts across regimes."""
    df = pd.DataFrame({"a": a, "b": b}).sort_index().ffill(limit=5).dropna()
    if len(df) < window * 2:
        return None
    roll = df["a"].diff().rolling(window).corr(df["b"].diff()).dropna()
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.plot(roll.index, roll.values, lw=1.4, color=BLUE)
    ax.axhline(0, color="#999", lw=0.8)
    ax.fill_between(roll.index, roll.values, 0,
                    where=roll.values > 0, color=BLUE, alpha=0.15)
    ax.fill_between(roll.index, roll.values, 0,
                    where=roll.values < 0, color=RED, alpha=0.15)
    ax.set_ylim(-1, 1)
    ax.set_ylabel(f"{window}d rolling corr")
    ax.set_title(f"Rolling correlation: {label_a} vs {label_b} "
                 "(daily changes)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = OUT_DIR / "rolling_corr.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
