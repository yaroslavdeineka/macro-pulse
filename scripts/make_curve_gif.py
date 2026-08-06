from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config                   # noqa: E402
from src.clients.ustreasury import USTreasuryClient  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "outputs" / "curve_evolution.gif"


def main() -> None:
    cfg = load_config()
    curve = USTreasuryClient().yield_curve(cfg["treasury_years"])
    curve["month"] = curve["date"].dt.to_period("M")
    # last observed curve of each month
    frames = []
    for month, grp in curve.groupby("month"):
        last = grp[grp["date"] == grp["date"].max()]
        frames.append((str(month), last.sort_values("maturity_years")))
    print(f"{len(frames)} monthly frames, "
          f"{frames[0][0]} → {frames[-1][0]}")

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ymax = curve["yield_pct"].max() + 0.5

    def draw(i: int):
        ax.clear()
        for k in range(max(0, i - 6), i):
            _, older = frames[k]
            ax.plot(older["maturity_years"], older["yield_pct"],
                    color="#2563EB", alpha=0.08 + 0.04 * (k - i + 6), lw=1)
        label, cur = frames[i]
        inverted = False
        wide = cur.set_index("tenor")["yield_pct"]
        if "10 Yr" in wide and "3 Mo" in wide:
            inverted = wide["10 Yr"] < wide["3 Mo"]
        color = "#DC2626" if inverted else "#2563EB"
        ax.plot(cur["maturity_years"], cur["yield_pct"], marker="o",
                ms=3, lw=2, color=color)
        ax.set_xscale("log")
        ax.set_xticks([0.25, 1, 2, 5, 10, 30])
        ax.set_xticklabels(["3M", "1Y", "2Y", "5Y", "10Y", "30Y"])
        ax.set_ylim(0, ymax)
        ax.set_ylabel("Par yield, %")
        ax.set_title(f"US Treasury yield curve — {label}"
                     + ("   [INVERTED]" if inverted else ""))
        ax.grid(alpha=0.3)

    anim = FuncAnimation(fig, draw, frames=len(frames), interval=90)
    OUT.parent.mkdir(exist_ok=True)
    anim.save(OUT, writer=PillowWriter(fps=11))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
