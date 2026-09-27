"""Two offline integration checks: mock model HTTP, execute real research tools."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_openrouter as runner
from core import load, restore_snapshot


class PromptRunnerTests(unittest.TestCase):
    def check_dialogue(self, follow_up):
        fixture = runner.ROOT / "examples/astronomy-uk-cs"
        config = load(fixture / "manifest.json")["config"]
        prompts = ["Досліди астрономію за збереженими даними."]
        if follow_up:
            prompts.append("Зміни критерій на growth без мережі.")
        requests = []
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "session"

            def response(request, timeout):
                body = json.loads(request.data)
                messages = body["messages"]
                requests.append(messages)
                if len(requests) == 1:
                    # Seed this session only; do not reuse host cache paths.
                    restore_snapshot(fixture, output / "cache")
                if messages[-1]["role"] == "user":
                    if messages[-1]["content"] == prompts[0]:
                        argv = ["run", "--qid", config["qid"], "--languages", *config["languages"],
                                "--start", config["start"], "--end", config["end"],
                                "--criterion", config["criterion"], "--offline", "--out", "initial"]
                    else:
                        argv = ["revise", "--run", "initial", "--criterion", "growth", "--offline", "--out", "revised"]
                    message = {"role": "assistant", "content": None, "tool_calls": [{
                        "id": f"call-{len(requests)}", "type": "function", "function": {
                            "name": "wiki_cli", "arguments": json.dumps({"argv": argv})}}]}
                else:
                    tool = json.loads(messages[-1]["content"])
                    self.assertEqual(tool["returncode"], 0, tool)
                    study = json.loads(tool["stdout"])
                    self.assertEqual(study["http_stats"]["http_requests"], 0)
                    message = {"role": "assistant", "content": "Готово: " + study["priority"]["criterion"]}
                return io.BytesIO(json.dumps({"model": "test-stub", "choices": [{"message": message}]}).encode())

            argv = ["runner", "--model", "test-stub", "--out", str(output), "--max-turns", "2"]
            for prompt in prompts:
                argv += ["--prompt", prompt]
            stdout = io.StringIO()
            with patch.object(sys, "argv", argv), patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-placeholder"}), \
                    patch.object(runner.urllib.request, "urlopen", side_effect=response), contextlib.redirect_stdout(stdout):
                self.assertEqual(runner.main(), 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "completed")
            answers = ["Готово: " + config["criterion"]] + (["Готово: growth"] if follow_up else [])
            self.assertEqual(result["answers"], answers)
            self.assertEqual([m["content"] for m in requests[-1] if m["role"] == "user"], prompts)
            trace = load(output / "trace.json")
            self.assertEqual(trace["prompts"], prompts)
            self.assertEqual(len(trace["events"]), 3 * len(prompts))
            for name in ["initial"] + (["revised"] if follow_up else []):
                study = output / name
                self.assertEqual(load(study / "metrics.json")["metrics"], load(fixture / "metrics.json")["metrics"])
                manifest = load(study / "manifest.json")
                self.assertEqual(manifest["http_stats"]["http_requests"], 0)
                self.assertEqual(Path(manifest["cache_dir"]), output / "cache")
                self.assertEqual(len(PdfReader(study / "brief.pdf").pages), 1)
                for filename in ("brief.md", "trend.png", "trend.svg", "monthly.csv", "sources.json"):
                    self.assertGreater((study / filename).stat().st_size, 0)
            if follow_up:
                self.assertEqual(load(output / "revised/metrics.json")["priority"]["criterion"], "growth")
                self.assertEqual(load(output / "revised/manifest.json")["parent_run"], str(output / "initial"))
                self.assertIn("Готово: " + config["criterion"], [m.get("content") for m in requests[2]])

    def test_custom_prompt_creates_artifacts_and_returns_answer(self):
        self.check_dialogue(follow_up=False)

    def test_follow_up_preserves_history_cache_and_revises_ranking(self):
        self.check_dialogue(follow_up=True)


if __name__ == "__main__":
    unittest.main()
