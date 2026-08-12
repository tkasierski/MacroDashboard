from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.macro_dashboard.analytics import build_coverage_report, build_feature_panel
from src.macro_dashboard.pipeline import build_weekly_dataset

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "indicators.json"
HORIZON_WEEKS = {"1 year": 52, "3 years": 156, "10 years": 520}

st.set_page_config(page_title="MacroDashboard", page_icon="