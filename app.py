from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.macro_dashboard.analytics import build_coverage_report, build_feature_panel
from src.macro_dashboard.pipeline import build_weekly_dataset

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "indicators.json"
HORIZON_WEEKS = {"1 year": 52, "3 years": 156, "10 years": 520}

st.set_page_config(page_title="MacroDashboard", layout="wide")


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


def horizon_frame(features: pd.DataFrame, series_id: str, horizon: str) -> pd.DataFrame:
    frame = features[(features["series_id"] == series_id) & features["value"].notna()].copy()
    frame = frame.sort_values("week_ending")
    if horizon != "Full history":
        frame = frame.tail(HORIZON_WEEKS[horizon])
    if not frame.empty:
        frame["window_percentile"] = frame["value"].rank(method="average", pct=True) * 100.0
    return frame


def percentile_label(horizon: str) -> str:
    if horizon == "Full history":
        return "Full-history percentile"
    return f"{horizon} percentile"


def state_label(row: pd.Series, percentile: float) -> str:
    direction = int(row.get("stress_direction", 0))
    if direction == 0:
        return "Context"
    momentum = float(row.get("stress_change_3m", 0.0))
    weak = (percentile >= 70 and direction > 0) or (percentile <= 30 and direction < 0)
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


def direction_hint(series_id: str, spec: dict) -> str:
    hints = {
        "WEI": "Higher = stronger broad economic activity; sustained declines toward or below zero are the warning signal.",
        "NFCI": "Above zero = tighter-than-average financial conditions; below zero = looser-than-average conditions.",
        "ANFCI": "Higher = tighter conditions than the current economy would normally imply; lower = easier-than-expected conditions.",
        "ICSA": "Higher and persistently rising claims = more layoffs and labor-market deterioration; lower/stable is healthier.",
        "IURSA": "Higher = a larger share of covered workers remaining on unemployment insurance, generally a weaker labor signal.",
        "CCSA": "Higher and rising = unemployed workers are taking longer to find jobs; falling claims generally indicate improvement.",
        "T10Y3M": "More negative = greater yield-curve inversion and historically greater recession risk; positive = normally sloped curve.",
        "T10Y2Y": "More negative = deeper curve inversion; re-steepening can reflect either improving expectations or late-cycle policy repricing.",
        "STLFSI4": "Above zero = above-average financial stress; larger positive readings indicate increasingly unusual market strain.",
        "DFII5": "Higher real yields tighten discount rates and financing conditions, but can also accompany stronger real growth expectations.",
        "T5YIE": "Higher = more inflation compensation priced by markets; lower = less, though liquidity and risk premia also matter.",
        "TSA": "Higher throughput = stronger travel/services activity; sustained weakness relative to history is the negative signal.",
        "INDEED_JOB_POSTINGS": "Higher = stronger employer hiring demand; persistent declines indicate cooling labor demand.",
    }
    if series_id in hints:
        return hints[series_id]
    direction = int(spec.get("stress_direction", 0))
    if direction > 0:
        return "Higher readings generally correspond to more macro stress."
    if direction < 0:
        return "Lower readings generally correspond to more macro stress."
    return "Interpret this mainly as regime context rather than a simple good/bad signal."


def metric_card(
    series_id: str,
    features: pd.DataFrame,
    specs: dict[str, dict],
    horizon: str,
) -> None:
    row = latest_feature(features, series_id)
    window = horizon_frame(features, series_id, horizon)
    if row is None or window.empty:
        st.warning(f"{series_id}: no current data")
        return
    spec = specs.get(series_id, {})
    name = spec.get("name", series_id)
    value = float(row["value"])
    pct = float(window.iloc[-1]["window_percentile"])
    change_3m = row.get("change_3m")
    with st.container(border=True):
        st.metric(name, format_value(value, spec), f"3m {format_change(change_3m, spec)}")
        st.caption(f"{state_label(row, pct)} · {pct:.0f}th {percentile_label(horizon).lower()}")
        st.write(spec.get("description", ""))
        st.caption(direction_hint(series_id, spec))


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
    horizon = st.selectbox("Chart & percentile history", ["1 year", "3 years", "10 years", "Full history"], index=1)
    chart_mode = st.radio("Chart mode", ["Raw series", "Percentile within selected history"], horizontal=False)
    st.caption("The history selector controls both the visible chart window and the reference window used to calculate percentiles.")
    st.caption("Changes are changes in the underlying series, shown in each indicator's natural units—not changes in percentile.")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

headline = ["WEI", "NFCI", "ICSA", "IURSA", "T10Y3M", "TSA", "INDEED_JOB_POSTINGS"]
headline = [sid for sid in headline if specs.get(sid, {}).get("role") in selected_roles]

st.subheader("Current snapshot")
st.caption(f"Latest reading, 3-month change, and percentile position calculated over the selected {horizon.lower()} window.")
for start in range(0, len(headline), 2):
    cols = st.columns(2)
    for col, sid in zip(cols, headline[start : start + 2]):
        with col:
            metric_card(sid, features, specs, horizon)

st.divider()
st.subheader("Indicator explorer")
eligible = [sid for sid in weekly.columns if specs.get(sid, {}).get("role") in selected_roles]
selected = st.selectbox("Indicator", eligible, format_func=lambda sid: specs.get(sid, {}).get("name", sid))
spec = specs[selected]

st.markdown(f"**What it measures:** {spec.get('description', 'Description not yet available.')}  ")
st.markdown(f"**Why it matters / how to read it:** {spec.get('why_it_matters', direction_hint(selected, spec))}  ")
st.markdown(f"**Directional shorthand:** {direction_hint(selected, spec)}")
st.caption(
    f"Producer: {spec.get('producer', spec.get('source_name', 'Unknown'))} · "
    f"Unit: {spec.get('unit', 'not specified')} · "
    f"Caveat: {spec.get('caveat', 'Use as one input among several, not in isolation.')}"
)

series_features = horizon_frame(features, selected, horizon).set_index("week_ending")
if chart_mode == "Raw series":
    chart = series_features[["value"]].rename(columns={"value": spec["name"]})
else:
    chart = series_features[["window_percentile"]].rename(columns={"window_percentile": percentile_label(horizon)})
st.line_chart(chart, height=360)

current = latest_feature(features, selected)
if current is not None and not series_features.empty:
    current_pct = float(series_features.iloc[-1]["window_percentile"])
    summary = [
        (percentile_label(horizon), f"{current_pct:.0f}th"),
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
    f"Percentile note: rankings are recalculated using the observations inside the selected {horizon.lower()} window. "
    "Changing the history selector therefore changes both the percentile chart and the current percentile reading."
)
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
