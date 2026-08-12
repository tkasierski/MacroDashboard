from __future__ import annotations

import pandas as pd


def _percentile_rank(series: pd.Series) -> pd.Series:
    return series.rank(method="average", pct=True) * 100.0


def _expanding_percentile(series: pd.Series, min_periods: int = 52) -> pd.Series:
    def rank_last(window: pd.Series) -> float:
        if window.isna().all():
            return float("nan")
        last = window.iloc[-1]
        if pd.isna(last):
            return float("nan")
        return float((window.dropna() <= last).mean() * 100.0)

    return series.expanding(min_periods=min_periods).apply(rank_last, raw=False)


def build_feature_panel(weekly: pd.DataFrame, specs: dict[str, dict]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []

    for series_id in weekly.columns:
        series = weekly[series_id].astype(float)
        spec = specs.get(series_id, {})
        direction = int(spec.get("stress_direction", 0))

        frame = pd.DataFrame({
            "week_ending": weekly.index,
            "series_id": series_id,
            "value": series.values,
        })
        indexed = series.copy()
        frame["percentile_full_history"] = _percentile_rank(indexed).values
        frame["percentile_expanding"] = _expanding_percentile(indexed).values
        for label, periods in (("1w", 1), ("3m", 13), ("6m", 26), ("12m", 52)):
            frame[f"change_{label}"] = indexed.diff(periods).values
            if direction:
                frame[f"stress_change_{label}"] = (indexed.diff(periods) * direction).values
            else:
                frame[f"stress_change_{label}"] = float("nan")

        frame["stress_direction"] = direction
        frame["role"] = spec.get("role", "")
        frame["name"] = spec.get("name", series_id)
        rows.append(frame)

    return pd.concat(rows, ignore_index=True)


def build_coverage_report(weekly: pd.DataFrame, specs: dict[str, dict]) -> pd.DataFrame:
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    rows: list[dict] = []

    for series_id in weekly.columns:
        series = weekly[series_id].dropna()
        spec = specs.get(series_id, {})
        first = series.index.min() if not series.empty else pd.NaT
        last = series.index.max() if not series.empty else pd.NaT
        rows.append({
            "series_id": series_id,
            "name": spec.get("name", series_id),
            "role": spec.get("role", ""),
            "source_name": spec.get("source_name", ""),
            "source_url": spec.get("source_url", ""),
            "redistribution": spec.get("redistribution", "unknown"),
            "download_allowed": bool(spec.get("download_allowed", False)),
            "first_observation": first,
            "latest_observation": last,
            "observations": int(series.shape[0]),
            "null_share": float(weekly[series_id].isna().mean()),
            "stale_days": int((now - last).days) if pd.notna(last) else None,
        })

    return pd.DataFrame(rows).sort_values(["role", "series_id"]).reset_index(drop=True)
