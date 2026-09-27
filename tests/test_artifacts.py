"""End-to-end artifact and recovery checks on controlled, explicitly synthetic data."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import analyze, prioritize
from core import ResearchError, load, month_range
from evaluate_openrouter import execute_tool, local_path
from wiki_interest import render_study


def example(langs):
    months = month_range("2024-01", "2025-12")
    metrics, series, pages = [], [], []
    for lang in langs:
        page = {"language": lang, "title": "Synthetic fixture", "url": f"https://{lang}.wikipedia.org/wiki/Test", "status": "ok", "mapping": "wikidata", "created_at": "2000-01-01T00:00:00Z"}
        values, totals = [1000] * 12 + [1200] * 12, [1000000] * 24
        metric, shares = analyze(months, values, totals, page)
        metrics.append(metric)
        pages.append(page)
        series.append({"language": lang, "views": values, "share_per_million": shares})
    return {"topic": "Synthetic report - not real Wikimedia data", "months": months, "metrics": metrics, "series": series, "pages": pages, "priority": prioritize(metrics), "scope_note": "Synthetic data used only to verify PDF layout and arithmetic. No product recommendation is intended.", "warnings": [], "created_at": "2026-09-26T00:00:00+00:00", "method_version": "1.0"}


class ArtifactTests(unittest.TestCase):
    def test_five_language_report_has_one_page_and_sources(self):
        from report import render
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as d:
            render(example(["uk", "pl", "cs", "en", "de"]), Path(d))
            pdf = PdfReader(Path(d) / "brief.pdf")
            self.assertEqual(len(pdf.pages), 1)
            text = pdf.pages[0].extract_text()
            self.assertIn("+20.0%", text)
            self.assertIn("Articles and coverage", text)
            self.assertIn("24/24 observed months", text)
            self.assertGreater(len(pdf.pages[0].get("/Annots", [])), 5)
            self.assertTrue((Path(d) / "trend.png").exists())

    def test_render_failure_and_success_update_manifest(self):
        result = example(["uk"])
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            manifest = {"status": "data_ready"}
            with patch("report.render", side_effect=ImportError("test native module failure")):
                with self.assertRaises(ResearchError):
                    render_study(result, output, manifest)
            self.assertEqual(load(output / "manifest.json")["status"], "report_failed")
            with patch("report.render"):
                render_study(result, output, manifest)
            saved = load(output / "manifest.json")
            self.assertEqual(saved["status"], "complete")
            self.assertNotIn("report_error", saved)

    def test_model_tools_cannot_escape_output_or_run_shell(self):
        with tempfile.TemporaryDirectory() as d:
            for value in ("../../etc/passwd", "/etc/passwd"):
                with self.assertRaises(ResearchError):
                    local_path(value, Path(d))
            with self.assertRaises(ResearchError):
                execute_tool("wiki_cli", {"argv": ["bash", "-c", "true"]}, Path(d))
            with self.assertRaises(ResearchError):
                execute_tool("read_reference", {"name": "../../etc/passwd"}, Path(d))


if __name__ == "__main__":
    unittest.main()
