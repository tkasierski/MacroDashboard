# MacroDashboard

MacroDashboard is a source-first U.S. macro situational-awareness dashboard.

The initial build focuses on reliable ingestion, weekly normalization, historical context, and transparent source metadata before any Streamlit UI or composite scoring model is added.

## Local setup

1. Create a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Set `FRED_API_KEY` in your environment.
4. Run `python -m src.macro_dashboard.pipeline`.

Generated datasets are written under `data/processed/` and are intentionally excluded from Git.
