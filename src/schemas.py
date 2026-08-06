from __future__ import annotations

import pandas as pd


class SchemaError(ValueError):
    """A client returned a frame that violates its declared contract."""


#: schema name -> {column: dtype family ("datetime", "numeric", "string")}
SCHEMAS: dict[str, dict[str, str]] = {
    "yield_curve": {"date": "datetime", "tenor": "string",
                    "maturity_years": "numeric", "yield_pct": "numeric"},
    "fx": {"date": "datetime", "currency": "string", "rate": "numeric"},
    "policy_rate": {"date": "datetime", "rate_pct": "numeric"},
    "wb_long": {"country_iso3": "string", "country": "string",
                "year": "numeric", "value": "numeric", "indicator": "string"},
    "monthly_indicator": {"date": "datetime", "geo": "string", "value": "numeric"},
    "annual_indicator": {"country_iso3": "string", "year": "numeric",
                         "value": "numeric"},
}


def _family_ok(series: pd.Series, family: str) -> bool:
    if family == "datetime":
        return pd.api.types.is_datetime64_any_dtype(series)
    if family == "numeric":
        return pd.api.types.is_numeric_dtype(series)
    if family == "string":
        return (pd.api.types.is_object_dtype(series)
                or pd.api.types.is_string_dtype(series))
    return False


def validate(df: pd.DataFrame, schema: str, source: str = "?") -> pd.DataFrame:
    """Validate and return df (chainable). Raises SchemaError on violation."""
    spec = SCHEMAS[schema]
    missing = [c for c in spec if c not in df.columns]
    if missing:
        raise SchemaError(
            f"[{source}] schema '{schema}': missing columns {missing}; "
            f"got {list(df.columns)}")
    for col, family in spec.items():
        if len(df) and not _family_ok(df[col], family):
            raise SchemaError(
                f"[{source}] schema '{schema}': column '{col}' should be "
                f"{family}, got dtype {df[col].dtype}")
    return df
