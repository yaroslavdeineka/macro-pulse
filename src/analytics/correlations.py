from __future__ import annotations

import pandas as pd


def build_panel(named_series: dict[str, pd.Series]) -> pd.DataFrame:
    """Align daily series on their common dates (inner join, ffill≤5d)."""
    clean = {}
    for name, s in named_series.items():
        if s is None:
            continue
        s = s.dropna()
        if len(s) < 30:
            continue
        s.index = pd.to_datetime(s.index)
        clean[name] = s[~s.index.duplicated(keep="last")]
    if len(clean) < 2:
        return pd.DataFrame()
    panel = pd.DataFrame(clean).sort_index().ffill(limit=5).dropna()
    return panel


def correlation_matrix(named_series: dict[str, pd.Series],
                       min_overlap: int = 60) -> pd.DataFrame:
    """Pearson correlations on daily CHANGES (not levels — levels of
    trending series produce spurious correlations)."""
    panel = build_panel(named_series)
    if panel.empty or len(panel) < min_overlap:
        return pd.DataFrame()
    changes = panel.diff().dropna()
    return changes.corr().round(2)


def strongest_pairs(corr: pd.DataFrame, top: int = 5) -> pd.DataFrame:
    """Top |correlation| pairs as a tidy table for the report."""
    if corr.empty:
        return pd.DataFrame()
    rows = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            rows.append({"pair": f"{a} × {b}", "corr": corr.loc[a, b]})
    out = pd.DataFrame(rows)
    out["abs"] = out["corr"].abs()
    return (out.sort_values("abs", ascending=False)
               .drop(columns="abs").head(top).reset_index(drop=True))
