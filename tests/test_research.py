"""Behavioral checks for false growth, cache reuse, provenance and input boundaries."""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import analyze, prioritize
from core import Client, ResearchError, digest, dump, month_range, parse_series, period
from resolver import resolve

MONTHS = month_range("2024-01", "2025-12")
PAGE = {"language": "uk", "title": "Example", "status": "ok", "mapping": "wikidata", "created_at": "2000-01-01T00:00:00Z"}


class AnalysisTests(unittest.TestCase):
    def metric(self, values, totals=None, months=MONTHS, page=PAGE):
        return analyze(months, values, totals or [1000000] * len(months), page)[0]

    def test_growth_and_season_matching(self):
        base = [1000 * i for i in range(1, 13)]
        m = self.metric(base + [v * 2 for v in base])
        self.assertAlmostEqual(m["yoy_pct"], 100)
        self.assertEqual(m["leave_one_pair_out_yoy_range"], [100, 100])
        self.assertEqual(m["positive_month_pairs"], 12)

    def test_project_growth_cannot_masquerade_as_topic_growth(self):
        m = self.metric([1000] * 12 + [1200] * 12, [1000000] * 12 + [1500000] * 12)
        self.assertAlmostEqual(m["yoy_pct"], 20)
        self.assertAlmostEqual(m["normalized_yoy_pct"], -20)
        self.assertIn("raw_normalized_direction_differs", m["flags"])
        self.assertEqual(prioritize([m])["research_next"], [])

    def test_single_spike_does_not_make_shortlist(self):
        m = self.metric([1000] * 23 + [13000])
        self.assertEqual(m["yoy_pct"], 100)
        self.assertEqual(m["peak_pair_excluded_yoy_pct"], 0)
        self.assertEqual(m["leave_one_pair_out_yoy_range"][0], 0)
        self.assertIn("direction_sensitive_to_one_pair", m["flags"])
        self.assertEqual(prioritize([m])["research_next"], [])

    def test_zero_baseline_is_undefined(self):
        m = self.metric([0] * 12 + [100] * 12)
        self.assertIsNone(m["yoy_pct"])
        self.assertIn("zero_baseline", m["flags"])

    def test_missing_not_zero(self):
        missing = self.metric([1000] * 23 + [None])
        zero = self.metric([1000] * 23 + [0])
        self.assertIsNone(missing["yoy_pct"])
        self.assertIsNone(missing["latest_12m_views"])
        self.assertIsNotNone(zero["yoy_pct"])
        self.assertEqual(zero["observed_months"], 24)
        self.assertIsNone(self.metric([None] * 24)["observed_views"])

    def test_insufficient_history_never_annualized(self):
        m = self.metric([1000] * 6, months=MONTHS[:6])
        self.assertIsNone(m["yoy_pct"])
        self.assertEqual(m["stability"], "insufficient")

    def test_missing_denominator_retains_absolute_metrics(self):
        m = self.metric([1000] * 12 + [1200] * 12, [1000000] * 23 + [None])
        self.assertAlmostEqual(m["yoy_pct"], 20)
        self.assertIsNone(m["normalized_yoy_pct"])
        self.assertEqual(m["stability"], "caution")

    def test_annual_share_is_ratio_of_sums(self):
        values = [1000] * 12 + [2000] * 12
        totals = [1000000] * 12 + [1000000] * 6 + [3000000] * 6
        self.assertAlmostEqual(self.metric(values, totals)["normalized_yoy_pct"], 0)

    def test_new_article_with_numeric_zeros_is_not_comparable(self):
        m = self.metric([1000] * 24, page={**PAGE, "created_at": "2024-06-01T00:00:00Z"})
        self.assertEqual(m["stability"], "insufficient")

    def test_manual_mapping_is_not_automatically_ranked(self):
        m = self.metric([1000] * 12 + [1200] * 12, page={**PAGE, "mapping": "manual"})
        self.assertEqual(prioritize([m])["research_next"], [])

    def test_consistent_growth_and_decline(self):
        up = self.metric([1000] * 12 + [1200] * 12)
        down = self.metric([1000] * 12 + [800] * 12)
        self.assertEqual(up["stability"], "consistent")
        self.assertEqual(down["stability"], "consistent")
        self.assertEqual(prioritize([up, down])["research_next"], ["uk"])

    def test_longer_series_summary_uses_last_24(self):
        m = self.metric([99999] * 12 + [1000] * 12 + [1200] * 12, months=month_range("2023-01", "2025-12"))
        self.assertAlmostEqual(m["yoy_pct"], 20)


class InputAndMappingTests(unittest.TestCase):
    def test_default_period_is_complete(self):
        p = period(today=date(2026, 9, 23))
        self.assertEqual((p[0], p[-1], len(p)), ("2024-09", "2026-08", 24))

    def test_reject_current_month_and_pre_api_dates(self):
        for first, last in [("2024-01", "2026-09"), ("2015-06", "2016-06"), ("2025-01", "2024-12")]:
            with self.assertRaises(ResearchError):
                period(first, last, today=date(2026, 9, 23))

    def test_no_sitelink_stays_missing(self):
        class NoNetwork:
            def get(self, *args, **kwargs):
                raise AssertionError("No request should be made for a missing sitelink")
        pages = resolve(NoNetwork(), {"qid": "Q1", "titles": {"pl": None}}, ["pl"])
        self.assertEqual(pages[0]["status"], "missing_article")

    def test_override_requires_explanation(self):
        with self.assertRaises(ResearchError):
            resolve(None, {"qid": "Q1", "titles": {}}, ["pl"], {"pl": "Anything"})

    def test_disambiguation_is_rejected(self):
        class Fake:
            def get(self, *a, **k):
                return {"data": {"query": {"pages": [{"ns": 0, "pageprops": {"disambiguation": ""}}]}}}
        pages = resolve(Fake(), {"qid": "Q1", "titles": {"pl": "Test"}}, ["pl"])
        self.assertEqual(pages[0]["status"], "ambiguous_article")


def response_item(month, value=1000):
    return {"timestamp": month.replace("-", "") + "0100", "views": value, "access": "all-access", "agent": "user", "granularity": "monthly"}


class ClientTests(unittest.TestCase):
    def test_notfound_retains_original_error_evidence(self):
        body = {"title": "Not found", "detail": "No data for requested range"}
        def opener(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 404, "Not found", {}, io.BytesIO(json.dumps(body).encode()))
        with tempfile.TemporaryDirectory() as d:
            entry = Client(d, opener=opener, sleeper=lambda x: None).get("https://wikimedia.org/api/rest_v1/example", allow_404=True)
            self.assertEqual(entry["data"], body)
            self.assertEqual(entry["http_status"], 404)
            self.assertEqual(parse_series(entry, ["2024-01"]), {"2024-01": None})

    def test_missing_rows_and_404_are_not_zero(self):
        result = parse_series({"data": {"items": [response_item("2024-01", 0)]}}, ["2024-01", "2024-02"])
        self.assertEqual(result, {"2024-01": 0, "2024-02": None})
        self.assertEqual(parse_series({"data": {"items": []}, "http_status": 404}, ["2024-01"]), {"2024-01": None})

    def test_invalid_and_duplicate_counts_rejected(self):
        for items in [[response_item("2024-01", -1)], [response_item("2024-01", True)], [response_item("2024-01")] * 2]:
            with self.assertRaises(ResearchError):
                parse_series({"data": {"items": items}}, ["2024-01"])

    def test_overlap_and_offline_reuse_without_network(self):
        requested = []
        def opener(req, timeout):
            requested.append(req.full_url)
            start, end = req.full_url.split("/")[-2:]
            months = month_range(start[:4] + "-" + start[4:6], end[:4] + "-" + end[4:6])
            return io.BytesIO(json.dumps({"items": [response_item(m) for m in months]}).encode())
        with tempfile.TemporaryDirectory() as d:
            first = Client(d, opener=opener, sleeper=lambda x: None)
            first.series("uk", "A/B & C", MONTHS[:12])
            second = Client(d, opener=opener, sleeper=lambda x: None)
            values = second.series("uk", "A/B & C", MONTHS[:14])
            self.assertEqual(len(requested), 2)
            self.assertTrue(requested[-1].endswith("2025010100/2025022800"))
            self.assertIn("A%2FB_%26_C", requested[0])
            self.assertEqual(values, [1000] * 14)
            offline = Client(d, offline=True, opener=lambda *a, **k: self.fail("Network called"))
            self.assertEqual(offline.series("uk", "A/B & C", MONTHS[:14]), values)
            self.assertEqual(offline.stats["http_requests"], 0)

    def test_retry_after_and_no_retry_for_forbidden(self):
        calls, delays = [], []
        def opener(req, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "slow", {"Retry-After": "3"}, None)
            return io.BytesIO(b'{"items": []}')
        with tempfile.TemporaryDirectory() as d:
            c = Client(d, opener=opener, sleeper=delays.append)
            c.get("https://www.wikidata.org/w/api.php")
            self.assertIn(3, delays)
            self.assertEqual(c.stats["retries"], 1)
            def forbidden(req, timeout):
                raise urllib.error.HTTPError(req.full_url, 403, "no", {}, None)
            c = Client(d, refresh=True, opener=forbidden, sleeper=lambda x: None)
            with self.assertRaises(ResearchError):
                c.get("https://www.wikidata.org/w/api.php")
            self.assertEqual(c.stats["http_requests"], 1)

    def test_response_checksum_detects_modified_cache(self):
        with tempfile.TemporaryDirectory() as d:
            c = Client(d, opener=lambda *a, **k: io.BytesIO(b'{"items": []}'), sleeper=lambda x: None)
            c.get("https://www.wikidata.org/w/api.php")
            path = next((Path(d) / "responses").glob("*.json"))
            entry = json.loads(path.read_text())
            entry["data"] = {"invented": 5}
            dump(path, entry)
            with self.assertRaises(ResearchError):
                Client(d, offline=True).get("https://www.wikidata.org/w/api.php")


if __name__ == "__main__":
    unittest.main()
