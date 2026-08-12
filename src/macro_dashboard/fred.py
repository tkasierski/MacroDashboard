from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_series(series_id: str) -> pd.DataFrame:
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("FRED_API_KEY is not set")

    response = requests.get(
        FRED_OBSERVATIONS_URL,
        params={"series_id": series_id, "api_key": api_key, "file_type": "json"},
        timeout=30,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()

    frame = pd.DataFrame(payload["observations"], columns=["date", "value"])
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["series_id"] = series_id
    return frame[["date", "series_id", "value"]]


def to_weekly(frame: pd.DataFrame, anchor: str, aggregation: str) -> pd.DataFrame:
    series = frame.set_index("date")["value"].sort_index()
    if aggregation == "mean":
        weekly = series.resample(anchor).mean()
    elif aggregation == "last":
        weekly = series.resample(anchor).last()
    else:
        raise ValueError(f"Unsupported aggregation: {aggregation}")

    return weekly.rename(frame["series_id"].iloc[0]).to_frame()
