from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.macro_dashboard.analytics import build_coverage_report, build_feature_panel
from src.macro_dashboard.pipeline import build_weekly_dataset

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "indicators.json"

st.set_page_config(page_title="MacroDashboard", page_icon="📈", layout="wide")


def load_specs() -> tuple[dict, dict[str, dict]]:
    config = json.loads(CONFIG_PATH.read_text())
    specs = {spec["id"]: spec for spec in config["fred"]}
    specs["TSA"] = {
        "id": "TSA",
        "name": "TSA Passenger Throughput",
        "role": "core_direct",
        "stress_direction": -1,
        "source_name": "Transportation Security Administration",
        "source_url": "https://www.tsa.gov/travel/passenger-volumes",
        "redistribution": "public",
        "download_allowed": True,
    }
    specs["INDEED_JOB_POSTINGS"] = {
        "id": "INDEED_JOB_POSTINGS",
        "name": "Indeed US Job Postings Index",
        "role": "challenger_direct",
        "stress_direction": -1,
        "source_name": "Indeed Hiring Lab",
        "source_url": "https://github.com/hiring-lab/job_postings_tracker",
        "redistribution": "attribution",
        "download_allowed": True,
    }
    return config, specs


@st.cache_data(ttl=3600, show_spinner="Refreshing macro data...")
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, dict]]:
    _, specs = load_specs()
    weekly = build_weekly_dataset()
    features = build_feature_panel(weekly, specs)
    coverage = build_coverage_report(weekly, specs)
    return weekly, features, coverage, specs


def latest_feature(features: pd.DataFrame, series_id: str) -> pd.Series | None:
    frame = features[(features["series_id"] == series_id) & features["value"].notna()]
    if frame.empty:
        return None
    return frame.iloc[-1]


def state_label(row: pd.Series) -> str:
    direction = int(row.get("stress_direction", 0))
    if direction == 0:
        return "Context"
    level = float(row.get("percentile_full_history", 50.0))
    momentum = float(row.get("stress_change_3m", 0.0))
    weak = (level >= 70 and direction > 0) or (level <= 30 and direction < 0)
    deteriorating = momentum > 0
    if weak and deteriorating:
        return "Weak / Deteriorating"
    if weak and not deteriorating:
        return "Weak / Improving"
    if not weak and deteriorating:
        return "Healthy / Deteriorating"
    return "Healthy / Improving"


def metric_card(series_id: str, features: pd.DataFrame, specs: dict[str, dict]) -> None:
    row = latest_feature(features, series_id)
    if row is None:
        st.warning(f"{series_id}: no current data")
        return
    name = specs.get(series_id, {}).get("name", series_id)
    value = float(row["value"])
    pct = float(row["percentile_full_history"])
    change_3m = row.get("change_3m")
    delta = None if pd.isna(change_3m) else f"3m {float(change_3m):+.2f}"
    st.metric(name, f"{value:,.2f}", delta)
    st.caption(f"{state_label(row)} · {pct:.0f}th percentile")


try:
    weekly, features, coverage, specs = load_data()
except Exception as exc:
    st.error("Data refresh failed. Confirm FRED_API_KEY is available to the Streamlit process.")
    st.exception(exc)
    st.stop()

st.title("MacroDashboard")
st.caption("U.S. macro situational awareness · weekly normalization · source-first design")

latest_week = weekly.dropna(how="all").index.max()
active_series = int(weekly.notna().any().sum())
st.write(f"Latest weekly anchor: **{latest_week.date()}** · Active series: **{active_series}**")

with st.sidebar:
    st.header("View")
    role_options = sorted({str(v.get("role", "")) for v in specs.values() if v.get("role")})
    selected_roles = st.multiselect("Roles", role_options, default=role_options)
    horizon = st.selectbox("Chart history", ["1 year", "3 years", "10 years", "Full history"], index=1)
    chart_mode = st.radio("Chart mode", ["Raw", "Percentile"], horizontal=True)
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

headline = ["WEI", "NFCI", "ICSA", "IURSA", "T10Y3M", "TSA", "INDEED_JOB_POSTINGS"]
headline = [sid for sid in headline if specs.get(sid, {}).get("role") in selected_roles]

st.subheader("Current snapshot")
for start in range(0, len(headline), 4):
    cols = st.columns(4)
    for col, sid in zip(cols, headline[start : start + 4]):
        with col:
            metric_card(sid, features, specs)

st.divider()
st.subheader("Indicator explorer")
eligible = [sid for sid in weekly.columns if specs.get(sid, {}).get("role") in selected_roles]
selected = st.selectbox("Indicator", eligible, format_func=lambda sid: specs.get(sid, {}).get("name", sid))

series_features = features[features["series_id"] == selected].copy().set_index("week_ending")
if horizon != "Full history":
    offsets = {"1 year": 52, "3 years": 156, "10 years": 520}
    series_features = series_features.tail(offsets[horizon])

if chart_mode == "Raw":
    chart = series_features[["value"]].rename(columns={"value": specs[selected]["name"]})
else:
    chart = series_features[["percentile_full_history"]].rename(columns={"percentile_full_history": "Percentile"})
st.line_chart(chart, height=380)

current = latest_feature(features, selected)
if current is not None:
    c1, c2, c3, c4, c5 = st.columns(5)
    values = [
        ("Percentile", current.get("percentile_full_history")),
        ("1w change", current.get("change_1w")),
        ("3m change", current.get("change_3m")),
        ("6m change", current.get("change_6m")),
        ("12m change", current.get("change_12m")),
    ]
    for col, (label, value) in zip([c1, c2, c3, c4, c5], values):
        with col:
            st.metric(label, "—" if pd.isna(value) else f"{float(value):,.2f}")

spec = specs[selected]
st.caption(
    f"Source: {spec.get('source_name', 'Unknown')} · Role: {spec.get('role', '')} · "
    f"Redistribution: {spec.get('redistribution', 'unknown')}"
)
if spec.get("download_allowed", False):
    download = weekly[[selected]].dropna().reset_index().to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download chart data (CSV)",
        data=download,
        file_name=f"{selected.lower()}_weekly.csv",
        mime="text/csv",
    )

st.divider()
st.subheader("Data coverage")
coverage_view = coverage.copy()
coverage_view["first_observation"] = pd.to_datetime(coverage_view["first_observation"]).dt.date
coverage_view["latest_observation"] = pd.to_datetime(coverage_view["latest_observation"]).dt.date
st.dataframe(
    coverage_view[
        [
            "series_id",
            "name",
            "role",
            "first_observation",
            "latest_observation",
            "observations",
            "stale_days",
            "redistribution",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

st.caption("This dashboard is descriptive and directional, not a recession oracle or market-timing system.")
