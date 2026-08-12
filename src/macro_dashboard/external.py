from __future__ import annotations

from io import BytesIO

import pandas as pd
import requests

ADS_URL = "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/ads/ADS_Index_Most_Current_Vintage.xlsx"


def fetch_ads() -> pd.DataFrame:
    response = requests.get(ADS_URL, timeout=30)
    response.raise_for_status()
    frame = pd.read_excel(BytesIO(response.content))

    # The Philadelphia Fed file is a two-column daily series. Keep parsing flexible
    # in case column labels change while the shape remains stable.
    frame = frame.iloc[:, :2].copy()
    frame.columns = ["date", "value"]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["date", "value"])
    frame["series_id"] = "ADS"
    return frame[["date", "series_id", "value"]]
