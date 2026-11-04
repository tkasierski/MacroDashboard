from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from .analytics import build_coverage_report, build_feature_panel
from .external import fetch_indeed_job_postings
from .fred import fetch_series, to_weekly

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "indicators.json"
PROCESSED_DIR = ROOT / "data" / "processed"
LOGGER = logging.getLogger(__name__)



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

    for series_id, fetcher, aggregation in (
        ("INDEED_JOB_POSTINGS", fetch_indeed_job_postings, "last"),
    ):
        try:
            frame = fetcher()
            if frame.empty:
                raise ValueError("Source returned no observations")
            weekly_frames.append(to_weekly(frame, anchor, aggregation))
        except (ValueError, KeyError, IndexError, OSError, pd.errors.ParserError) as exc:
            LOGGER.warning("%s data unavailable: %s", series_id, exc)
        except Exception as exc:
            # External providers can reject or change their endpoints independently.
            LOGGER.warning("%s data unavailable (%s): %s", series_id, type(exc).__name__, exc)

    # Preserve unavailable series as NaN, never as zero or stale observations.
    for series_id in ("INDEED_JOB_POSTINGS",):
        if not any(series_id in frame.columns for frame in weekly_frames):
            weekly_frames.append(pd.DataFrame({series_id: pd.Series(dtype="float64")}))

    weekly = pd.concat(weekly_frames, axis=1).sort_index()
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    weekly = weekly.loc[weekly.index <= today]
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
