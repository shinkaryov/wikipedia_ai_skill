#!/usr/bin/env python3
"""Run custom research prompts or evaluation scenarios through OpenRouter."""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from core import ROOT, ResearchError, dump, load, now

TOOLS = [
    {"type": "function", "function": {"name": "wiki_cli", "description": "Execute the Wikipedia Interest Research CLI. Provide arguments starting with discover, search-pages, run, revise, render or replay. No shell or python prefix. Use relative run names for --out and --run.", "parameters": {"type": "object", "properties": {"argv": {"type": "array", "items": {"type": "string"}}}, "required": ["argv"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "read_reference", "description": "Read one named skill reference when needed.", "parameters": {"type": "object", "properties": {"name": {"type": "string", "enum": ["methodology.md", "README.md"]}}, "required": ["name"], "additionalProperties": False}}},
]


def local_path(value, base):
    path = Path(value)
    path = (path if path.is_absolute() else base / path).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ResearchError("invalid_path", "Keep generated studies inside the evaluation output directory.")
    return str(path)


def execute_tool(name, arguments, output):
    if name == "read_reference":
        allowed = {"methodology.md", "README.md"}
        if arguments.get("name") not in allowed:
            raise ResearchError("invalid_reference", "Unknown reference.")
        return {"text": ((ROOT / "README.md") if arguments["name"] == "README.md" else (ROOT / "references" / arguments["name"])).read_text(encoding="utf-8")}
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
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                value = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read(16384))
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                error = error if isinstance(error, dict) else {}
            except (ValueError, UnicodeError):
                error = {}
            message = str(error.get("message") or "OpenRouter rejected the request.").replace(key, "[redacted]")[:600]
            metadata = error.get("metadata")
            provider = metadata.get("provider_name") if isinstance(metadata, dict) else None
            retry_after = None
            header = exc.headers.get("Retry-After") if exc.headers else None
            if header:
                try:
                    retry_after = float(header)
                except ValueError:
                    try:
                        date = parsedate_to_datetime(header)
                        retry_after = (date - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        pass
                if retry_after is not None:
                    retry_after = max(0, retry_after) if math.isfinite(retry_after) else None
            delay = retry_after if retry_after is not None else 2 ** attempt
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if retryable and attempt < 3 and delay <= 60:
                print(json.dumps({"status": "retrying", "http_status": exc.code,
                                  "attempt": attempt, "wait_seconds": delay}), file=sys.stderr, flush=True)
                time.sleep(delay)
                continue
            hints = {401: "Check OPENROUTER_API_KEY.", 402: "Check available credits.",
                     403: "Check account and provider access.",
                     404: "Check the model ID and availability of a tool-capable endpoint.",
                     429: "Retry later or choose another available provider/model."}
            raise ResearchError("model_http_error", message, status=exc.code, attempts=attempt,
                                provider=str(provider).replace(key, "[redacted]")[:120] if provider else None,
                                retry_after_seconds=retry_after,
                                hint=hints.get(exc.code, "Retry later if the provider is unavailable.")) from exc
    if "choices" not in value or not value["choices"]:
        raise ResearchError("model_response_error", "No model completion received.")
    return value

def read_user_message():
    """Read valid UTF-8; reject damaged input before saving history."""
    while True:
        print("You (/exit to finish): ", end="", file=sys.stderr, flush=True)
        try:
            if hasattr(sys.stdin, "buffer"):
                line = sys.stdin.buffer.readline().decode("utf-8", errors="strict")
            else:
                line = sys.stdin.readline()
            line.encode("utf-8", errors="strict")
        except UnicodeError:
            print(
                "Input contains invalid UTF-8. Please type your reply again.",
                file=sys.stderr,
                flush=True,
            )
            continue
        except KeyboardInterrupt:
            print(file=sys.stderr)
            return None
        if not line or line.strip().lower() == "/exit":
            return None
        if line.strip():
            return line.strip()


def run(model, prompts, output, max_turns, interactive=False):
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
              "Skip environment setup and do not read README.md for research; use methodology.md only when needed. "
              "Distinguish language editions from countries and observed trends from unsupported causes. "
              "Reply concisely with grounded findings and output paths.\n\n" + (ROOT / "SKILL.md").read_text())
    prompts = list(prompts)
    messages = [{"role": "system", "content": system}]
    trace = {"requested_model": model, "started_at": now(), "prompts": prompts, "interactive": interactive, "events": [], "status": "running"}
    t0 = time.monotonic()
    try:
        for index, prompt in enumerate(prompts):
            messages.append({"role": "user", "content": prompt})
            dump(output / "trace.json", trace)
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
                    if interactive:
                        print("\nAssistant: " + (message.get("content") or "[No text response]"), file=sys.stderr, flush=True)
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
            if interactive and index + 1 == len(prompts):
                follow_up = read_user_message()
                if follow_up is not None:
                    prompts.append(follow_up)
        trace["status"] = "completed"
    except KeyboardInterrupt:
        trace["status"] = "interrupted"
        raise
    except Exception as exc:
        trace["status"] = "failed"
        trace["error"] = exc.as_dict() if isinstance(exc, ResearchError) else str(exc)
        raise
    finally:
        trace["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        dump(output / "trace.json", trace)
    return {"status": trace["status"], "trace": str(output / "trace.json"), "note": "Completion is not a pass judgement: review outputs using README.md."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Exact OpenRouter model ID with tool support")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--scenario", help="Named scenario; defaults to astronomy when --prompt is absent")
    source.add_argument("--prompt", action="append", help="Custom request; repeat for sequential follow-ups in the same conversation")
    parser.add_argument("--interactive", action="store_true", help="Read clarifications and follow-ups from stdin; /exit or EOF finishes")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-turns", type=int, default=10)
    args = parser.parse_args()
    try:
        if not 1 <= args.max_turns <= 20:
            raise ResearchError("invalid_budget", "Use 1-20 turns per user message.")
        if args.prompt is not None:
            prompts = [prompt.strip() for prompt in args.prompt]
            if any(not prompt for prompt in prompts):
                raise ResearchError("empty_prompt", "Each --prompt must contain a nonempty request.")
        elif args.interactive and args.scenario is None:
            first_prompt = read_user_message()
            if first_prompt is None:
                print(json.dumps({"status": "cancelled"}))
                return 0
            prompts = [first_prompt]
        else:
            scenarios = load(ROOT / "examples/agent_scenarios.json")
            scenario = args.scenario or "astronomy"
            if scenario not in scenarios:
                raise ResearchError("unknown_scenario", "Choose a known scenario or use --prompt.", available=list(scenarios))
            prompts = scenarios[scenario]
        result = run(args.model, prompts, args.out, args.max_turns, interactive=args.interactive)
        trace = load(result["trace"])
        result["answers"] = [
            event["message"]["content"]
            for event in trace["events"]
            if event["type"] == "model"
            and not event["message"].get("tool_calls")
            and event["message"].get("content")
        ]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted"}))
        return 130
    except ResearchError as exc:
        print(json.dumps({"status": "error", "error": exc.as_dict()}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
