from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.macro_dashboard.analytics import build_coverage_report, build_feature_panel
from src.macro_dashboard.pipeline import build_weekly_dataset

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "indicators.json"

st.set_page_config(page_title="MacroDashboard", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600, show_spinner="Refreshing macro data...")
def load_data(config_version: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, dict]]:
    del config_version
    weekly, specs = build_weekly_dataset()
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


def format_value(value: float, spec: dict) -> str:
    decimals = int(spec.get("value_decimals", 2))
    unit = spec.get("unit", "")
    if unit == "%":
        return f"{value:,.{decimals}f}%"
    if unit in {"claims", "passengers"}:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def format_change(value: float | None, spec: dict) -> str:
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    change_format = spec.get("change_format", "raw")
    unit = spec.get("unit", "")
    if change_format == "bp":
        return f"{value * 100:+.0f} bp"
    if change_format == "pp":
        return f"{value:+.2f} pp"
    if change_format in {"integer", "count", "passengers"}:
        suffix = f" {unit}" if unit else ""
        return f"{value:+,.0f}{suffix}"
    if change_format == "index":
        return f"{value:+.2f} index pts"
    return f"{value:+,.2f}"


def direction_hint(spec: dict) -> str:
    direction = int(spec.get("stress_direction", 0))
    if direction > 0:
        return "Higher generally means more macro stress."
    if direction < 0:
        return "Lower generally means more macro stress."
    return "Use mainly as regime context rather than a simple good/bad signal."


def metric_card(series_id: str, features: pd.DataFrame, specs: dict[str, dict]) -> None:
    row = latest_feature(features, series_id)
    if row is None:
        st.warning(f"{series_id}: no current data")
        return
    spec = specs.get(series_id, {})
    name = spec.get("name", series_id)
    value = float(row["value"])
    pct = float(row["percentile_full_history"])
    change_3m = row.get("change_3m")
    with st.container(border=True):
        st.metric(name, format_value(value, spec), f"3m {format_change(change_3m, spec)}")
        st.caption(f"{state_label(row)} · {pct:.0f}th historical percentile")
        st.write(spec.get("description", ""))
        st.caption(direction_hint(spec))


try:
    config_version = CONFIG_PATH.stat().st_mtime_ns
    weekly, features, coverage, specs = load_data(config_version)
except Exception as exc:
    st.error("Data refresh failed. Confirm FRED_API_KEY is available to the Streamlit process.")
    st.exception(exc)
    st.stop()

st.title("MacroDashboard")
st.caption("U.S. macro situational awareness · weekly normalization · source-first design")

latest_week = weekly.dropna(how="all").index.max()
active_series = int(weekly.notna().any().sum())
st.write(f"Latest completed weekly anchor: **{latest_week.date()}** · Active series: **{active_series}**")

with st.sidebar:
    st.header("View")
    role_options = sorted({str(v.get("role", "")) for v in specs.values() if v.get("role")})
    selected_roles = st.multiselect("Roles", role_options, default=role_options)
    horizon = st.selectbox("Chart history", ["1 year", "3 years", "10 years", "Full history"], index=1)
    chart_mode = st.radio("Chart mode", ["Raw series", "Historical percentile"], horizontal=False)
    st.caption("Changes are changes in the underlying series, shown in each indicator's natural units—not changes in percentile.")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

headline = ["WEI", "NFCI", "ICSA", "IURSA", "T10Y3M", "TSA", "INDEED_JOB_POSTINGS"]
headline = [sid for sid in headline if specs.get(sid, {}).get("role") in selected_roles]

st.subheader("Current snapshot")
st.caption("Latest reading, 3-month change, historical position, and a short description of what each indicator actually measures.")
for start in range(0, len(headline), 2):
    cols = st.columns(2)
    for col, sid in zip(cols, headline[start : start + 2]):
        with col:
            metric_card(sid, features, specs)

st.divider()
st.subheader("Indicator explorer")
eligible = [sid for sid in weekly.columns if specs.get(sid, {}).get("role") in selected_roles]
selected = st.selectbox("Indicator", eligible, format_func=lambda sid: specs.get(sid, {}).get("name", sid))
spec = specs[selected]

st.markdown(f"**What it measures:** {spec.get('description', 'Description not yet available.')}  ")
st.markdown(f"**Why it matters / how to read it:** {spec.get('why_it_matters', direction_hint(spec))}  ")
st.markdown(f"**Directional shorthand:** {direction_hint(spec)}")
st.caption(
    f"Producer: {spec.get('producer', spec.get('source_name', 'Unknown'))} · "
    f"Unit: {spec.get('unit', 'not specified')} · "
    f"Caveat: {spec.get('caveat', 'Use as one input among several, not in isolation.')}"
)

series_features = features[features["series_id"] == selected].copy().set_index("week_ending")
if horizon != "Full history":
    offsets = {"1 year": 52, "3 years": 156, "10 years": 520}
    series_features = series_features.tail(offsets[horizon])

if chart_mode == "Raw series":
    chart = series_features[["value"]].rename(columns={"value": spec["name"]})
else:
    chart = series_features[["percentile_full_history"]].rename(columns={"percentile_full_history": "Historical percentile"})
st.line_chart(chart, height=360)

current = latest_feature(features, selected)
if current is not None:
    summary = [
        ("Historical percentile", f"{float(current.get('percentile_full_history')):.0f}th"),
        ("1w change", format_change(current.get("change_1w"), spec)),
        ("3m change", format_change(current.get("change_3m"), spec)),
        ("6m change", format_change(current.get("change_6m"), spec)),
        ("12m change", format_change(current.get("change_12m"), spec)),
    ]
    for start in range(0, len(summary), 3):
        cols = st.columns(min(3, len(summary) - start))
        for col, (label, value) in zip(cols, summary[start : start + 3]):
            with col:
                st.metric(label, value)

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
with st.expander("Data coverage and source diagnostics", expanded=False):
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
