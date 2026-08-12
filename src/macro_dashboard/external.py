from __future__ import annotations

from io import BytesIO

import pandas as pd
import requests

ADS_URL = "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/ads/ADS_Index_Most_Current_Vintage.xlsx"


def _coerce_dates(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_share = numeric.notna().mean()
    if numeric_share > 0.8:
        dates = pd.to_datetime(numeric, unit="D", origin="1899-12-30", errors="coerce")
    else:
        dates = pd.to_datetime(series, errors="coerce")
    return dates


def fetch_ads() -> pd.DataFrame:
    response = requests.get(ADS_URL, timeout=30)
    response.raise_for_status()
    workbook = pd.ExcelFile(BytesIO(response.content))

    best: pd.DataFrame | None = None
    best_rows = 0

    for sheet in workbook.sheet_names:
        raw = pd.read_excel(workbook, sheet_name=sheet, header=None)
        for date_col in raw.columns:
            dates = _coerce_dates(raw[date_col])
            for value_col in raw.columns:
                if value_col == date_col:
                    continue
                values = pd.to_numeric(raw[value_col], errors="coerce")
                candidate = pd.DataFrame({"date": dates, "value": values}).dropna()
                candidate = candidate[candidate["date"].between("1950-01-01", "2100-01-01")]
                if len(candidate) > best_rows:
                    best = candidate
                    best_rows = len(candidate)

    if best is None or best_rows < 100:
        raise ValueError("Could not identify ADS date/value columns in Philadelphia Fed workbook")

    frame = best.drop_duplicates(subset="date", keep="last").sort_values("date")
    frame["series_id"] = "ADS"
    return frame[["date", "series_id", "value"]]
