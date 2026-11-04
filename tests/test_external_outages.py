"""Regression tests for optional external feed outages."""
import unittest
from unittest.mock import patch

import pandas as pd
import requests

from src.macro_dashboard import pipeline


class PipelineOutageTests(unittest.TestCase):
    @patch.object(pipeline, "fetch_indeed_job_postings")
    @patch.object(pipeline, "fetch_series")
    def test_external_outage_does_not_block_fred(self, fred, indeed):
        fred.side_effect = lambda sid: pd.DataFrame({
            "date": pd.to_datetime(["2026-10-23", "2026-10-30"]),
            "series_id": [sid, sid],
            "value": [1.0, 2.0],
        })
        indeed.side_effect = requests.ConnectionError("External feed unavailable")

        weekly, specs = pipeline.build_weekly_dataset()
        self.assertTrue(weekly["WEI"].notna().any())
        self.assertTrue(weekly["INDEED_JOB_POSTINGS"].isna().all())
        self.assertIn("INDEED_JOB_POSTINGS", specs)

    @patch.object(pipeline, "fetch_indeed_job_postings")
    @patch.object(pipeline, "fetch_tsa")
    @patch.object(pipeline, "fetch_series")
    def test_successful_external_feed_is_preserved(self, fred, indeed):
        fred.side_effect = lambda sid: pd.DataFrame({
            "date": pd.to_datetime(["2026-10-30"]),
            "series_id": [sid],
            "value": [1.0],
        })
        indeed.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-10-30"]),
            "series_id": ["INDEED_JOB_POSTINGS"],
            "value": [110.0],
        })
        weekly, specs = pipeline.build_weekly_dataset()
        self.assertEqual(float(weekly["INDEED_JOB_POSTINGS"].dropna().iloc[-1]), 110.0)
        self.assertIn("RCMFLBBALDPDPCT90P", specs)
        self.assertNotIn("TSA", specs)


if __name__ == "__main__":
    unittest.main()
