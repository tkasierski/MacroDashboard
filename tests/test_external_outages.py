"""Regression tests for optional external feed outages."""
import unittest
from unittest.mock import patch

import pandas as pd
import requests

from src.macro_dashboard import pipeline


class PipelineOutageTests(unittest.TestCase):
    @patch.object(pipeline, "fetch_indeed_job_postings")
    @patch.object(pipeline, "fetch_tsa")
    @patch.object(pipeline, "fetch_series")
    def test_external_403_does_not_block_fred(self, fred, tsa, indeed):
        fred.side_effect = lambda sid: pd.DataFrame({
            "date": pd.to_datetime(["2026-10-23", "2026-10-30"]),
            "series_id": [sid, sid],
            "value": [1.0, 2.0],
        })
        response = requests.Response()
        response.status_code = 403
        response.url = "https://www.tsa.gov/travel/passenger-volumes?page=0"
        tsa.side_effect = requests.HTTPError("403 Forbidden", response=response)
        indeed.side_effect = requests.ConnectionError("External feed unavailable")

        weekly, specs = pipeline.build_weekly_dataset()
        self.assertTrue(weekly["WEI"].notna().any())
        self.assertTrue(weekly["TSA"].isna().all())
        self.assertTrue(weekly["INDEED_JOB_POSTINGS"].isna().all())
        self.assertIn("TSA", specs)
        self.assertIn("INDEED_JOB_POSTINGS", specs)

    @patch.object(pipeline, "fetch_indeed_job_postings")
    @patch.object(pipeline, "fetch_tsa")
    @patch.object(pipeline, "fetch_series")
    def test_successful_external_feed_is_preserved(self, fred, tsa, indeed):
        fred.side_effect = lambda sid: pd.DataFrame({
            "date": pd.to_datetime(["2026-10-30"]),
            "series_id": [sid],
            "value": [1.0],
        })
        tsa.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-10-30"]),
            "series_id": ["TSA"],
            "value": [2500000.0],
        })
        indeed.side_effect = requests.ConnectionError("Unavailable")
        weekly, _ = pipeline.build_weekly_dataset()
        self.assertEqual(float(weekly["TSA"].dropna().iloc[-1]), 2500000.0)
        self.assertTrue(weekly["INDEED_JOB_POSTINGS"].isna().all())


if __name__ == "__main__":
    unittest.main()
