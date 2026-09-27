"""Dates, provenance and a conservative, sequential Wikimedia HTTP client."""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parents[1]
AQS = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
WD = "https://www.wikidata.org/w/api.php"


class ResearchError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details

    def as_dict(self):
        return {"code": self.code, "message": str(self), **self.details}


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ResearchError("invalid_month", "Use YYYY-MM.", value=value)
    try:
        return date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise ResearchError("invalid_month", "Invalid calendar month.", value=value) from exc


def shift_month(value, count):
    d = parse_month(value)
    year, month = divmod(d.year * 12 + d.month - 1 + count, 12)
    return f"{year:04d}-{month + 1:02d}"


def month_range(start, end):
    parse_month(start)
    parse_month(end)
    if start > end:
        raise ResearchError("invalid_range", "Start month must not follow end month.")
    result = []
    while start <= end:
        result.append(start)
        start = shift_month(start, 1)
    return result


def period(start=None, end=None, months=None, today=None):
    today = today or datetime.now(timezone.utc).date()
    latest = shift_month(today.strftime("%Y-%m"), -1)
    if months is not None and start is not None:
        raise ResearchError("invalid_range", "Use --months or --start, not both.")
    if months is not None and not 1 <= months <= 120:
        raise ResearchError("invalid_range", "MVP supports 1-120 months per study.")
    end = end or latest
    start = start or shift_month(end, -(months or 24) + 1)
    result = month_range(start, end)
    if start < "2015-07" or end > latest or len(result) > 120:
        raise ResearchError("unsupported_period", "Use 1-120 complete months from 2015-07 through the last complete UTC month.", latest=latest)
    return result


def languages(values):
    values = list(dict.fromkeys(values))
    if not 1 <= len(values) <= 5 or any(not re.fullmatch(r"[a-z][a-z0-9-]{0,19}", x) for x in values):
        raise ResearchError("invalid_languages", "Supply 1-5 Wikipedia language codes, for example uk pl cs.")
    return values


class Client:
    def __init__(self, cache_dir=None, offline=False, refresh=False, opener=None, sleeper=time.sleep):
        self.cache = Path(cache_dir or ROOT / ".cache").resolve()
        self.offline, self.refresh = offline, refresh
        if offline and refresh:
            raise ResearchError("invalid_mode", "--offline and --refresh cannot be combined.")
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleeper
        self.stats = {"http_requests": 0, "response_cache_hits": 0, "month_cache_hits": 0, "retries": 0}
        self.sources = {}
        self.warnings = set()

    def _record(self, envelope):
        key = digest({"url": envelope["url"], "fetched_at": envelope["fetched_at"], "sha256": envelope["sha256"]})
        self.sources[key] = envelope
        return key

    @staticmethod
    def _age(envelope):
        return (datetime.now(timezone.utc) - datetime.fromisoformat(envelope["fetched_at"])).total_seconds()

    def get(self, url, params=None, ttl=86400, allow_404=False, force=False):
        if params:
            url += "?" + urllib.parse.urlencode(sorted(params.items()))
        cache_path = self.cache / "responses" / (digest(url) + ".json")
        if cache_path.exists() and not self.refresh and not force:
            entry = load(cache_path)
            if digest(entry["data"]) != entry["sha256"]:
                raise ResearchError("cache_corrupt", "Cached response checksum failed. Rerun with --refresh.")
            if self.offline or self._age(entry) < ttl:
                if self.offline and self._age(entry) >= ttl:
                    self.warnings.add("stale_cache_used_offline")
                self.stats["response_cache_hits"] += 1
                self._record(entry)
                return entry
        if self.offline:
            raise ResearchError("offline_cache_miss", "Required data is not cached. Run online first.", url=url)
        headers = {"User-Agent": os.getenv("WIKIMEDIA_USER_AGENT", "WikiInterestResearch/0.1 (educational research prototype)"), "Accept": "application/json"}
        for attempt in range(4):
            try:
                self.stats["http_requests"] += 1
                self.sleep(0.12)
                with self.opener(urllib.request.Request(url, headers=headers), timeout=30) as response:
                    data = json.load(response)
                if "error" in data:
                    err = data["error"]
                    raise ResearchError("wikimedia_error", "Wikimedia returned an API error.", api_error=err)
                status = 200
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and allow_404:
                    raw_error = exc.read().decode("utf-8", errors="replace")
                    try:
                        data = json.loads(raw_error)
                    except ValueError:
                        data = {"raw_error_text": raw_error}
                    status = 404
                    break
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise ResearchError("http_error", "Wikimedia request failed; no values were fabricated.", status=exc.code, url=url) from exc
                retry_after = exc.headers.get("Retry-After", "")
                try:
                    delay = float(retry_after)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError):
                        delay = 2 ** attempt + random.random()
                if delay > 60:
                    raise ResearchError("rate_limited", "Server requests a longer pause. Retry later using the existing cache.", retry_after_seconds=delay) from exc
                self.stats["retries"] += 1
                self.sleep(max(0, delay))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == 3:
                    raise ResearchError("network_error", "Cannot reach Wikimedia. Retry later or use --offline with a populated cache.", url=url) from exc
                self.stats["retries"] += 1
                self.sleep(2 ** attempt)
            except (ValueError, TypeError) as exc:
                raise ResearchError("invalid_response", "Wikimedia did not return valid JSON.", url=url) from exc
        entry = {"url": url, "fetched_at": now(), "http_status": status, "sha256": digest(data), "data": data}
        dump(cache_path, entry)
        self._record(entry)
        return entry

    def series(self, lang, title, months):
        project = lang + ".wikipedia.org"
        endpoint = (f"{AQS}/aggregate/{project}/all-access/user/monthly" if title is None else
                    f"{AQS}/per-article/{project}/all-access/user/{urllib.parse.quote(title.replace(' ', '_'), safe='')}/monthly")
        directory = self.cache / "months" / digest(endpoint)
        result, missing = {}, []
        for month in months:
            path = directory / (month + ".json")
            entry = load(path) if path.exists() else None
            ttl = 86400 if month >= shift_month(datetime.now(timezone.utc).strftime("%Y-%m"), -2) else 30 * 86400
            if entry and not self.refresh and (self.offline or self._age(entry) < ttl):
                source_path = self.cache / "responses" / (digest(entry["source_url"]) + ".json")
                if source_path.exists():
                    source = load(source_path)
                    if source["sha256"] == entry["source_sha256"] and digest(source["data"]) == source["sha256"]:
                        # Re-derive the observation from its response, rather than trusting a cached number.
                        obs = parse_series(source, [month])[month]
                        result[month] = obs
                        self._record(source)
                        self.stats["month_cache_hits"] += 1
                        if self.offline and self._age(entry) >= ttl:
                            self.warnings.add("stale_cache_used_offline")
                        continue
            missing.append(month)
        groups = []
        for month in missing:
            if not groups or len(groups[-1]) >= 12 or shift_month(groups[-1][-1], 1) != month:
                groups.append([])
            groups[-1].append(month)
        for group in groups:
            first = group[0].replace("-", "") + "0100"
            d = parse_month(group[-1])
            last = d.strftime("%Y%m") + f"{calendar.monthrange(d.year, d.month)[1]:02d}00"
            # Month-level freshness is authoritative; a stale month must not be filled from stale HTTP cache.
            source = self.get(f"{endpoint}/{first}/{last}", allow_404=True, force=not self.offline)
            observations = parse_series(source, group)
            for month, value in observations.items():
                result[month] = value
                dump(directory / (month + ".json"), {"fetched_at": source["fetched_at"], "source_url": source["url"], "source_sha256": source["sha256"]})
        return [result[m] for m in months]


def parse_series(envelope, months):
    if envelope.get("http_status") == 404:
        return {m: None for m in months}
    data = envelope["data"]
    if not isinstance(data.get("items"), list):
        raise ResearchError("invalid_series", "Response has no items array.")
    result = {m: None for m in months}
    seen = set()
    for item in data["items"]:
        stamp, value = str(item.get("timestamp", "")), item.get("views")
        if not re.fullmatch(r"\d{10}", stamp) or type(value) is not int or value < 0:
            raise ResearchError("invalid_series", "Invalid timestamp or view count.")
        if item.get("agent") != "user" or item.get("access") != "all-access" or item.get("granularity") != "monthly":
            raise ResearchError("invalid_series", "Unexpected agent, access or granularity in response.")
        month = stamp[:4] + "-" + stamp[4:6]
        if month in seen:
            raise ResearchError("invalid_series", "Duplicate month in response.", month=month)
        seen.add(month)
        if month in result:
            result[month] = value
    return result


def restore_snapshot(run_directory, cache_directory):
    """Restore a portable audit bundle into a fresh cache without network access."""
    run_directory, cache_directory = Path(run_directory).resolve(), Path(cache_directory).resolve()
    sources = load(run_directory / "sources.json")
    for source in sorted(sources, key=lambda s: s["fetched_at"]):
        path = (run_directory / source["file"]).resolve()
        if not path.is_relative_to(run_directory):
            raise ResearchError("invalid_snapshot", "Source paths must stay inside the study.")
        entry = load(path)
        if digest(entry["data"]) != entry["sha256"] or source["sha256"] != entry["sha256"] or source["url"] != entry["url"]:
            raise ResearchError("invalid_snapshot", "Source response checksum or URL mismatch.")
        dump(cache_directory / "responses" / (digest(entry["url"]) + ".json"), entry)
        if entry["url"].startswith(AQS + "/"):
            endpoint = entry["url"].rsplit("/", 2)[0]
            first, last = entry["url"].rsplit("/", 2)[1:]
            months = month_range(first[:4] + "-" + first[4:6], last[:4] + "-" + last[4:6])
            parse_series(entry, months)
            for month in months:
                dump(cache_directory / "months" / digest(endpoint) / (month + ".json"), {"fetched_at": entry["fetched_at"], "source_url": entry["url"], "source_sha256": entry["sha256"]})
