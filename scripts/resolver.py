"""Resolve concepts using Wikidata sitelinks; never translate a title and assume identity."""
from __future__ import annotations

import re
from urllib.parse import quote
from core import ResearchError, WD


def entity(client, qid, langs):
    if not re.fullmatch(r"Q[1-9][0-9]*", qid):
        raise ResearchError("invalid_qid", "Use a Wikidata item ID returned by discover, such as Q333.")
    data = client.get(WD, {"action": "wbgetentities", "ids": qid, "props": "labels|descriptions|sitelinks", "languages": "en", "sitefilter": "|".join(l + "wiki" for l in langs), "format": "json"})["data"]
    item = data.get("entities", {}).get(qid, {})
    if "missing" in item or not item:
        raise ResearchError("missing_entity", "Wikidata item does not exist.", qid=qid)
    return {"qid": qid, "label": item.get("labels", {}).get("en", {}).get("value", qid), "description": item.get("descriptions", {}).get("en", {}).get("value", ""), "titles": {l: item.get("sitelinks", {}).get(l + "wiki", {}).get("title") for l in langs}}


def discover(client, topic, langs, search_language="en", limit=4):
    if not topic.strip() or len(topic) > 300:
        raise ResearchError("invalid_topic", "Topic must contain 1-300 characters.")
    data = client.get(WD, {"action": "wbsearchentities", "search": topic, "language": search_language, "uselang": "en", "type": "item", "limit": limit, "format": "json"})["data"]
    candidates = [entity(client, hit["id"], langs) for hit in data.get("search", [])]
    return {"topic": topic, "candidates": candidates, "next_action": "Choose the concept whose meaning matches the product question. If ambiguous, ask the user. Missing sitelinks are not zero interest."}


def page_search(client, topic, lang):
    data = client.get(f"https://{lang}.wikipedia.org/w/api.php", {"action": "query", "list": "search", "srsearch": topic, "srnamespace": 0, "srlimit": 5, "srprop": "", "format": "json"})["data"]
    return {"language": lang, "candidates": [{"title": x["title"], "url": f"https://{lang}.wikipedia.org/wiki/{quote(x['title'].replace(' ', '_'), safe='')}"} for x in data.get("query", {}).get("search", [])], "next_action": "Inspect meaning before using --page. A candidate is not a verified equivalent."}


def resolve(client, concept, langs, overrides=None, scope_note=""):
    overrides = overrides or {}
    if overrides and not scope_note.strip():
        raise ResearchError("scope_note_required", "Explicit page overrides require --scope-note explaining equivalence or proxy limitations.")
    if set(overrides) - set(langs):
        raise ResearchError("invalid_override", "Page override language must be in --languages.")
    pages = []
    for lang in langs:
        title = overrides.get(lang) or concept["titles"].get(lang)
        base = {"language": lang, "project": lang + ".wikipedia.org", "mapping": "manual" if lang in overrides else "wikidata", "requested_title": title, "status": "missing_article"}
        if not title:
            pages.append(base)
            continue
        try:
            data = client.get(f"https://{lang}.wikipedia.org/w/api.php", {"action": "query", "titles": title, "redirects": 1, "prop": "info|pageprops|revisions", "rvprop": "timestamp", "rvlimit": 1, "rvdir": "newer", "formatversion": 2, "format": "json"})["data"]
        except ResearchError as exc:
            pages.append({**base, "status": "api_error", "error": exc.as_dict()})
            continue
        found = data.get("query", {}).get("pages", [])
        page = found[0] if found else {}
        if "missing" in page or "invalid" in page or not page:
            pages.append(base)
            continue
        if page.get("ns") != 0 or "disambiguation" in page.get("pageprops", {}):
            pages.append({**base, "status": "ambiguous_article"})
            continue
        mapped_qid = page.get("pageprops", {}).get("wikibase_item")
        if lang not in overrides and mapped_qid != concept["qid"]:
            pages.append({**base, "status": "mapping_mismatch", "page_qid": mapped_qid})
            continue
        pages.append({**base, "status": "ok", "title": page["title"], "pageid": page["pageid"], "page_qid": mapped_qid, "created_at": next(iter(page.get("revisions", [])), {}).get("timestamp"), "redirected_from": title if page["title"] != title else None, "url": f"https://{lang}.wikipedia.org/wiki/{quote(page['title'].replace(' ', '_'), safe='')}"})
    return pages
