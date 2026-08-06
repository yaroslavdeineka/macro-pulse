from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:            # pragma: no cover
    HAS_DUCKDB = False

ROOT = Path(__file__).resolve().parents[1]

DDL = """
CREATE TABLE IF NOT EXISTS metric_history (
    run_ts    TIMESTAMP,
    metric    VARCHAR,      -- e.g. 'spread_10y_3m_bp', 'stress_index'
    entity    VARCHAR,      -- e.g. 'US', 'UKR', 'EUR/USD'
    as_of     DATE,         -- the data's own latest date
    value     DOUBLE
);
"""


def record_run(metrics: list[dict], db_path: str | Path) -> int:
    """Append rows [{metric, entity, as_of, value}, ...]; returns count."""
    if not HAS_DUCKDB or not metrics:
        return 0
    path = ROOT / db_path if not Path(db_path).is_absolute() else Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(metrics)
    df["run_ts"] = datetime.now(timezone.utc).replace(tzinfo=None)
    con = duckdb.connect(str(path))
    try:
        con.execute(DDL)
        con.execute("""INSERT INTO metric_history
                       SELECT run_ts, metric, entity, as_of, value FROM df""")
        return len(df)
    finally:
        con.close()


def load_metric(metric: str, db_path: str | Path,
                entity: str | None = None) -> pd.DataFrame:
    """Full recorded history of one metric across runs."""
    if not HAS_DUCKDB:
        return pd.DataFrame()
    path = ROOT / db_path if not Path(db_path).is_absolute() else Path(db_path)
    if not path.exists():
        return pd.DataFrame()
    con = duckdb.connect(str(path), read_only=True)
    try:
        q = "SELECT * FROM metric_history WHERE metric = ?"
        args = [metric]
        if entity:
            q += " AND entity = ?"
            args.append(entity)
        return con.execute(q + " ORDER BY run_ts", args).df()
    finally:
        con.close()


def run_count(db_path: str | Path) -> int:
    if not HAS_DUCKDB:
        return 0
    path = ROOT / db_path if not Path(db_path).is_absolute() else Path(db_path)
    if not path.exists():
        return 0
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.execute(
            "SELECT COUNT(DISTINCT run_ts) FROM metric_history").fetchone()[0]
    finally:
        con.close()
