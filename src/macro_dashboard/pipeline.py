from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .external import fetch_tsa
from .fred import fetch_series, to_weekly

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "indicators.json"
PROCESSED_DIR = ROOT / "data" / "processed"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def build_weekly_dataset() -> pd.DataFrame:
    config = load_config()
    anchor = config["weekly_anchor"]
    weekly_frames: list[pd.DataFrame] = []

    for spec in config["fred"]:
        raw = fetch_series(spec["id"])
        weekly_frames.append(to_weekly(raw, anchor, spec["aggregation"]))

    weekly_frames.append(to_weekly(fetch_tsa(), anchor, "mean"))

    weekly = pd.concat(weekly_frames, axis=1).sort_index()
    weekly.index.name = "week_ending"
    return weekly


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    weekly = build_weekly_dataset()
    output = PROCESSED_DIR / "macro_weekly.csv"
    weekly.to_csv(output)
    print(f"Wrote {len(weekly):,} weekly rows to {output}")


if __name__ == "__main__":
    main()
