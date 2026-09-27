#!/usr/bin/env python3
"""Small CLI for agents. JSON stdout; artifacts retain full evidence."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from core import Client, ResearchError, VERSION, dump, languages, load, now, period, restore_snapshot
from resolver import discover, entity, page_search, resolve
from analysis import METHOD_VERSION, analyze, prioritize


def overrides(values):
    result = {}
    for value in values or []:
        if ":" not in value:
            raise ResearchError("invalid_override", "Use --page 'language:Exact title'.")
        lang, title = value.split(":", 1)
        if lang in result or not title.strip() or len(title) > 255:
            raise ResearchError("invalid_override", "Duplicate language or invalid page title.")
        result[lang] = title
    return result


def completion_status(result):
    return "complete_with_warnings" if result["warnings"] or any(m["stability"] != "consistent" for m in result["metrics"]) else "complete"


def render_study(result, output, manifest):
    try:
        from report import render
        render(result, output)
    except (ResearchError, ImportError, OSError) as exc:
        error = exc if isinstance(exc, ResearchError) else ResearchError("render_environment_error", "Report rendering failed. Run uv sync --frozen, then render --run with the existing study; data need not be fetched again.", detail=str(exc))
        manifest["status"] = "report_failed"
        manifest["report_error"] = error.as_dict()
        dump(output / "manifest.json", manifest)
        raise error from exc
    manifest["status"] = completion_status(result)
    manifest.pop("report_error", None)
    dump(output / "manifest.json", manifest)


def execute_study(client, config, output, parent=None):
    output = Path(output).resolve()
    if (output / "manifest.json").exists():
        raise ResearchError("output_exists", "Choose a new --out directory; existing studies are immutable.", path=str(output))
    langs = languages(config["languages"])
    months = period(config.get("start"), config.get("end"), config.get("months"))
    concept = entity(client, config["qid"], langs)
    topic = config.get("topic") or concept["label"]
    if len(topic) > 110 or len(config.get("scope_note", "")) > 350:
        raise ResearchError("text_too_long", "Use a topic up to 110 characters and scope note up to 350 characters.")
    pages = resolve(client, concept, langs, config.get("pages"), config.get("scope_note", ""))
    metrics, series, errors = [], [], []
    for page in pages:
        if page.get("error"):
            errors.append({"language": page["language"], **page["error"]})
        values, totals = [None] * len(months), [None] * len(months)
        if page["status"] == "ok":
            try:
                values = client.series(page["language"], page["title"], months)
                totals = client.series(page["language"], None, months)
            except ResearchError as exc:
                errors.append({"language": page["language"], **exc.as_dict()})
                if all(v is None for v in values):
                    page["status"] = "api_error"
        metric, shares = analyze(months, values, totals, page)
        metrics.append(metric)
        series.append({"language": page["language"], "views": values, "project_views": totals, "share_per_million": shares})
    fixed = {**config, "topic": topic, "languages": langs, "start": months[0], "end": months[-1]}
    fixed.pop("months", None)
    result = {"schema_version": 1, "method_version": METHOD_VERSION, "tool_version": VERSION, "created_at": now(), "topic": topic, "concept": concept, "months": months, "pages": pages, "scope_note": config.get("scope_note", ""), "metrics": metrics, "series": series, "priority": prioritize(metrics, config.get("criterion", "balanced")), "warnings": sorted(client.warnings), "errors": errors}
    if errors:
        result["warnings"].append("partial_API_failure: see metrics.json errors")
    output.mkdir(parents=True, exist_ok=True)
    dump(output / "metrics.json", result)
    with (output / "monthly.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["month", "language", "article_views", "project_views", "article_views_per_million_project_views"])
        for row in series:
            writer.writerows(zip(months, [row["language"]] * len(months), row["views"], row["project_views"], row["share_per_million"]))
    sources = []
    for key, entry in client.sources.items():
        relative = f"sources/{key}.json"
        dump(output / relative, entry)
        sources.append({k: v for k, v in entry.items() if k != "data"} | {"file": relative})
    dump(output / "sources.json", sources)
    manifest = {"schema_version": 1, "tool_version": VERSION, "method_version": METHOD_VERSION, "created_at": result["created_at"], "config": fixed, "parent_run": str(parent) if parent else None, "cache_dir": str(client.cache), "http_stats": client.stats, "status": "data_ready", "outputs": ["metrics.json", "monthly.csv", "sources.json", "brief.pdf", "brief.md", "trend.png", "trend.svg"]}
    dump(output / "manifest.json", manifest)
    render_study(result, output, manifest)
    return {"status": manifest["status"], "run": str(output), "period": [months[0], months[-1]], "concept": concept["label"], "articles": [{k: p[k] for k in ("language", "title", "status", "url") if k in p} for p in pages], "metrics": metrics, "priority": result["priority"], "warnings": result["warnings"], "errors": errors, "http_stats": client.stats, "files": {n: str(output / n) for n in ["brief.pdf", "trend.png", "metrics.json", "manifest.json"]}}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("discover", "search-pages", "run", "revise"):
        p = sub.add_parser(name, allow_abbrev=False)
        p.add_argument("--cache-dir")
        p.add_argument("--offline", action="store_true")
        p.add_argument("--refresh", action="store_true")
        if name == "discover":
            p.add_argument("--topic", required=True)
            p.add_argument("--languages", nargs="+", required=True)
            p.add_argument("--search-language", default="en")
        elif name == "search-pages":
            p.add_argument("--topic", required=True)
            p.add_argument("--language", required=True)
        else:
            p.add_argument("--out", required=True)
            p.add_argument("--topic")
            p.add_argument("--languages", nargs="+", required=name == "run")
            p.add_argument("--start")
            p.add_argument("--end")
            p.add_argument("--months", type=int)
            p.add_argument("--criterion", choices=["balanced", "growth", "volume"])
            p.add_argument("--page", action="append")
            p.add_argument("--scope-note")
            if name == "run":
                p.add_argument("--qid", required=True)
            else:
                p.add_argument("--run", required=True)
    p = sub.add_parser("render", allow_abbrev=False)
    p.add_argument("--run", required=True, help="Regenerate outputs from metrics.json without network requests.")
    p = sub.add_parser("replay", allow_abbrev=False)
    p.add_argument("--run", required=True, help="Recompute from a saved source-response bundle without network access.")
    p.add_argument("--out", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "replay":
            original = Path(args.run).resolve()
            output = Path(args.out).resolve()
            if output.exists():
                raise ResearchError("output_exists", "Use a fresh directory for a replay.")
            cache = output / "snapshot-cache"
            restore_snapshot(original, cache)
            result = execute_study(Client(cache, offline=True), load(original / "manifest.json")["config"], output, original)
        elif args.command == "render":
            directory = Path(args.run).resolve()
            manifest = load(directory / "manifest.json")
            render_study(load(directory / "metrics.json"), directory, manifest)
            result = {"status": "rendered", "pdf": str(directory / "brief.pdf")}
        else:
            parent = load(Path(args.run) / "manifest.json") if args.command == "revise" else None
            cache = args.cache_dir or (parent.get("cache_dir") if parent else None)
            client = Client(cache, args.offline, args.refresh)
            if args.command == "discover":
                result = discover(client, args.topic, languages(args.languages), args.search_language)
            elif args.command == "search-pages":
                result = page_search(client, args.topic, languages([args.language])[0])
            else:
                config = dict(parent["config"]) if parent else {"qid": args.qid, "criterion": "balanced", "scope_note": "", "pages": {}}
                if parent and args.languages is not None and args.languages != parent["config"]["languages"] and args.topic is None:
                    # A previous title may name only the old languages. Keep the concept, regenerate a neutral title.
                    config["topic"] = None
                for key in ("topic", "languages", "start", "end", "months", "criterion", "scope_note"):
                    value = getattr(args, key)
                    if value is not None:
                        config[key] = value
                if args.months is not None:
                    config.pop("start", None)
                if args.page is not None:
                    config["pages"] = overrides(args.page)
                if args.languages is not None:
                    config["pages"] = {k: v for k, v in config.get("pages", {}).items() if k in args.languages}
                result = execute_study(client, config, args.out, args.run if parent else None)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except ResearchError as exc:
        print(json.dumps({"status": "error", "error": exc.as_dict()}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "error", "error": {"code": "local_or_schema_error", "message": str(exc)}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
