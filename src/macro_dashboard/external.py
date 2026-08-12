from __future__ import annotations

from io import BytesIO
import re
from urllib.parse import urljoin

import pandas as pd
import requests

ADS_URL = "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/ads/ADS_Index_Most_Current_Vintage.xlsx"
PALI_PAGE_URL = "https://www.fanniemae.com/data-and-insights/surveys-indices/weekly-mortgage-applications-data"
TSA_PAGE_URL = "https://www.tsa.gov/travel/passenger-volumes"
INDEED_US_URL = "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/aggregate_job_postings_US.csv"


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


def _latest_pali_workbook_url() -> str:
    response = requests.get(PALI_PAGE_URL, timeout=30)
    response.raise_for_status()
    matches = re.findall(r'href=["\']([^"\']*fannie-mae-pali-rali-weekly-[^"\']+\.xlsx)["\']', response.text, flags=re.I)
    if not matches:
        raise ValueError("Could not find latest PALI/RALI workbook link")
    return urljoin(PALI_PAGE_URL, matches[0])


def fetch_pali() -> pd.DataFrame:
    workbook_url = _latest_pali_workbook_url()
    response = requests.get(workbook_url, timeout=30)
    response.raise_for_status()
    workbook = pd.ExcelFile(BytesIO(response.content))

    for sheet in workbook.sheet_names:
        for header_row in range(0, 12):
            frame = pd.read_excel(workbook, sheet_name=sheet, header=header_row)
            columns = {str(col).strip().lower(): col for col in frame.columns}
            date_col = next((orig for norm, orig in columns.items() if "date" in norm or "week" in norm), None)
            pali_col = next((orig for norm, orig in columns.items() if "pali" in norm and ("dollar" in norm or "$" in norm or "volume" in norm)), None)
            if date_col is None or pali_col is None:
                continue
            dates = pd.to_datetime(frame[date_col], errors="coerce")
            values = pd.to_numeric(frame[pali_col], errors="coerce")
            candidate = pd.DataFrame({"date": dates, "value": values}).dropna()
            if len(candidate) >= 100:
                candidate = candidate.drop_duplicates(subset="date", keep="last").sort_values("date")
                candidate["series_id"] = "PALI"
                return candidate[["date", "series_id", "value"]]

    raise ValueError("Could not identify PALI dollar-volume date/value columns in Fannie Mae workbook")


def fetch_tsa() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for page in range(0, 20):
        response = requests.get(TSA_PAGE_URL, params={"page": page}, timeout=30)
        response.raise_for_status()
        tables = pd.read_html(response.text)
        table = next((t for t in tables if {"Date", "Numbers"}.issubset(t.columns)), None)
        if table is None or table.empty:
            break
        candidate = table[["Date", "Numbers"]].copy()
        candidate.columns = ["date", "value"]
        candidate["date"] = pd.to_datetime(candidate["date"], errors="coerce")
        candidate["value"] = pd.to_numeric(candidate["value"].astype(str).str.replace(",", "", regex=False), errors="coerce")
        candidate = candidate.dropna()
        if candidate.empty:
            break
        frames.append(candidate)

    if not frames:
        raise ValueError("Could not parse TSA checkpoint passenger volumes")

    frame = pd.concat(frames, ignore_index=True)
    frame = frame.drop_duplicates(subset="date", keep="first").sort_values("date")
    frame["series_id"] = "TSA"
    return frame[["date", "series_id", "value"]]


def fetch_indeed_job_postings() -> pd.DataFrame:
    response = requests.get(INDEED_US_URL, timeout=30)
    response.raise_for_status()
    frame = pd.read_csv(BytesIO(response.content))
    required = {"date", "indeed_job_postings_index_SA", "variable"}
    if not required.issubset(frame.columns):
        raise ValueError("Indeed CSV schema changed")

    frame = frame[frame["variable"].astype(str).str.lower().eq("total postings")].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["indeed_job_postings_index_SA"], errors="coerce")
    frame = frame.dropna(subset=["date", "value"])
    if len(frame) < 100:
        raise ValueError("Indeed US job postings series is unexpectedly short")

    frame = frame.drop_duplicates(subset="date", keep="last").sort_values("date")
    frame["series_id"] = "INDEED_JOB_POSTINGS"
    return frame[["date", "series_id", "value"]]
