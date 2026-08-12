from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .analytics import build_coverage_report, build_feature_panel
from .external import fetch_indeed_job_postings, fetch_tsa
from .fred import fetch_series, to_weekly

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "indicators.json"
PROCESSED_DIR = ROOT / "data" / "processed"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def build_specs(config: dict) -> dict[str, dict]:
    specs: dict[str, dict] = {}
    for spec in config.get("fred", []):
        enriched = dict(spec)
        enriched.update({
            "source_name": "Federal Reserve Economic Data (FRED)",
            "source_url": f"https://fred.stlouisfed.org/series/{spec['id']}",
            "redistribution": "mixed",
            "download_allowed": False,
        })
        specs[spec["id"]] = enriched
    for spec in config.get("external", []):
        specs[spec["id"]] = dict(spec)
    return specs


def build_weekly_dataset() -> tuple[pd.DataFrame, dict[str, dict]]:
    config = load_config()
    anchor = config["weekly_anchor"]
    weekly_frames: list[pd.DataFrame] = []

    for spec in config["fred"]:
        raw = fetch_series(spec["id"])
        weekly_frames.append(to_weekly(raw, anchor, spec["aggregation"]))

    weekly_frames.append(to_weekly(fetch_tsa(), anchor, "mean"))
    weekly_frames.append(to_weekly(fetch_indeed_job_postings(), anchor, "last"))

    weekly = pd.concat(weekly_frames, axis=1).sort_index()
    weekly.index.name = "week_ending"
    return weekly, build_specs(config)


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    weekly, specs = build_weekly_dataset()

    weekly_output = PROCESSED_DIR / "macro_weekly.csv"
    coverage_output = PROCESSED_DIR / "coverage.csv"
    features_output = PROCESSED_DIR / "features.csv"

    weekly.to_csv(weekly_output)
    build_coverage_report(weekly, specs).to_csv(coverage_output, index=False)
    build_feature_panel(weekly, specs).to_csv(features_output, index=False)

    print(f"Wrote {len(weekly):,} weekly rows to {weekly_output}")
    print(f"Wrote coverage report to {coverage_output}")
    print(f"Wrote historical-context features to {features_output}")


if __name__ == "__main__":
    main()
