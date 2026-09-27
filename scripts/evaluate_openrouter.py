#!/usr/bin/env python3
"""Optional, reproducible inexpensive-model evaluation. No API key embedded."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from core import ROOT, ResearchError, dump, load, now

TOOLS = [
    {"type": "function", "function": {"name": "wiki_cli", "description": "Execute the Wikipedia Interest Research CLI. Provide arguments starting with discover, search-pages, run, revise, render or replay. No shell or python prefix. Use relative run names for --out and --run.", "parameters": {"type": "object", "properties": {"argv": {"type": "array", "items": {"type": "string"}}}, "required": ["argv"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "read_reference", "description": "Read one named skill reference when needed.", "parameters": {"type": "object", "properties": {"name": {"type": "string", "enum": ["methodology.md", "mvp.md", "development.md", "evaluation.md"]}}, "required": ["name"], "additionalProperties": False}}},
]


def local_path(value, base):
    path = Path(value)
    path = (path if path.is_absolute() else base / path).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ResearchError("invalid_path", "Keep generated studies inside the evaluation output directory.")
    return str(path)


def execute_tool(name, arguments, output):
    if name == "read_reference":
        allowed = {"methodology.md", "mvp.md", "development.md", "evaluation.md"}
        if arguments.get("name") not in allowed:
            raise ResearchError("invalid_reference", "Unknown reference.")
        return {"text": (ROOT / "references" / arguments["name"]).read_text(encoding="utf-8")}
    argv = arguments.get("argv")
    if name != "wiki_cli" or not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv) or argv[0] not in {"discover", "search-pages", "run", "revise", "render", "replay"}:
        raise ResearchError("invalid_tool", "Use wiki_cli with a supported subcommand and string argument array.")
    argv = list(argv)
    # Disallow alternate spellings and caller-controlled cache paths. subprocess never uses a shell.
    for arg in argv:
        if arg.startswith("--") and "=" in arg:
            raise ResearchError("invalid_option", "Use separate flag and value arguments.")
        if arg == "--cache-dir":
            raise ResearchError("invalid_option", "The evaluator manages its own cache.")
    for i, arg in enumerate(argv):
        if arg in {"--out", "--run"}:
            if i + 1 == len(argv):
                raise ResearchError("invalid_option", "Missing path after option.")
            argv[i + 1] = local_path(argv[i + 1], output)
    if argv[0] not in {"render", "replay"}:
        argv += ["--cache-dir", str(output / "cache")]
    process = subprocess.run([sys.executable, str(ROOT / "scripts/wiki_interest.py"), *argv], cwd=ROOT, capture_output=True, text=True, timeout=300)
    return {"argv": argv, "returncode": process.returncode, "stdout": process.stdout[-30000:], "stderr": process.stderr[-3000:]}


def completion(model, messages, key):
    body = {"model": model, "messages": messages, "tools": TOOLS, "tool_choice": "auto", "max_tokens": 3000, "provider": {"require_parameters": True}}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + key, "X-Title": "WikiInterestResearch-Evaluation"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            value = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ResearchError("model_http_error", "OpenRouter request failed; inspect account access or retry later.", status=exc.code) from exc
    if "choices" not in value or not value["choices"]:
        raise ResearchError("model_response_error", "No model completion received.")
    return value


def run(model, prompts, output, max_turns):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ResearchError("missing_model_key", "Set OPENROUTER_API_KEY in your local environment, never in the skill or chat.")
    output = Path(output).resolve()
    if output.exists():
        raise ResearchError("output_exists", "Use a fresh evaluation directory.")
    output.mkdir(parents=True)
    system = (f"Today is {now()[:10]}. Fulfill the user's request using the following skill. "
              "Dependencies are installed. Execute its CLI through wiki_cli (argument array, no python or shell prefix). "
              "Use relative run names. The tool manages a shared cache for this conversation. "
              "Use read_reference if needed. Reply concisely with grounded findings and output paths.\n\n" + (ROOT / "SKILL.md").read_text())
    messages = [{"role": "system", "content": system}]
    trace = {"requested_model": model, "started_at": now(), "prompts": prompts, "events": [], "status": "running"}
    t0 = time.monotonic()
    try:
        for prompt in prompts:
            messages.append({"role": "user", "content": prompt})
            for _ in range(max_turns):
                response = completion(model, messages, key)
                raw = response["choices"][0]["message"]
                message = {k: raw[k] for k in ("role", "content", "tool_calls", "reasoning_details") if k in raw}
                messages.append(message)
                # Store only visible response/tool messages, not private model reasoning.
                visible = {k: message[k] for k in ("role", "content", "tool_calls") if k in message}
                trace["events"].append({"type": "model", "model": response.get("model"), "generation_id": response.get("id"), "usage": response.get("usage"), "message": visible})
                dump(output / "trace.json", trace)
                if not message.get("tool_calls"):
                    break
                for call in message["tool_calls"]:
                    try:
                        result = execute_tool(call["function"]["name"], json.loads(call["function"]["arguments"]), output)
                    except (ResearchError, ValueError, subprocess.TimeoutExpired) as exc:
                        result = {"error": exc.as_dict() if isinstance(exc, ResearchError) else str(exc)}
                    event = {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)}
                    messages.append(event)
                    trace["events"].append({"type": "tool", "message": event})
                    dump(output / "trace.json", trace)
            else:
                raise ResearchError("turn_limit", "Evaluation exceeded its model-turn budget.")
        trace["status"] = "completed"
    except Exception as exc:
        trace["status"] = "failed"
        trace["error"] = exc.as_dict() if isinstance(exc, ResearchError) else str(exc)
        raise
    finally:
        trace["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        dump(output / "trace.json", trace)
    return {"status": trace["status"], "trace": str(output / "trace.json"), "note": "Completion is not a pass judgement: review outputs using references/evaluation.md."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Exact OpenRouter model ID with tool support")
    parser.add_argument("--scenario", choices=list(load(ROOT / "examples/agent_scenarios.json")), default="astronomy")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-turns", type=int, default=10)
    args = parser.parse_args()
    try:
        if not 1 <= args.max_turns <= 20:
            raise ResearchError("invalid_budget", "Use 1-20 turns per user message.")
        result = run(args.model, load(ROOT / "examples/agent_scenarios.json")[args.scenario], args.out, args.max_turns)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ResearchError as exc:
        print(json.dumps({"status": "error", "error": exc.as_dict()}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
