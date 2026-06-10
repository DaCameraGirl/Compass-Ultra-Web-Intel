from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.crawl_websites_to_snowflake import (  # noqa: E402
    Page,
    crawl_site,
    fetch_crawler_feed,
    load_feed_file,
    normalize_url,
    root_domain,
)


STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "and",
    "any",
    "are",
    "before",
    "between",
    "but",
    "can",
    "for",
    "from",
    "has",
    "have",
    "how",
    "into",
    "not",
    "one",
    "our",
    "that",
    "the",
    "their",
    "then",
    "this",
    "through",
    "using",
    "when",
    "where",
    "with",
    "without",
    "your",
}

DEFAULT_EXCLUDE_DOMAINS = {
    "linkedin.com",
    "www.linkedin.com",
    "instagram.com",
    "www.instagram.com",
    "reddit.com",
    "www.reddit.com",
    "medium.com",
    "www.medium.com",
    "facebook.com",
    "www.facebook.com",
    "x.com",
    "twitter.com",
    "www.youtube.com",
    "youtube.com",
    "prnewswire.com",
    "www.prnewswire.com",
    "army.mil",
    "www.army.mil",
}


def words(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())
        if token not in STOPWORDS and not token.isdigit()
    ]


def ngrams(tokens: list[str], size: int) -> list[str]:
    return [" ".join(tokens[index : index + size]) for index in range(0, max(len(tokens) - size + 1, 0))]


def source_text(pages: list[Page]) -> str:
    chunks = []
    for page in pages:
        chunks.extend([page.title, page.meta_description, " ".join(page.headings), page.body_text])
    return " ".join(chunk for chunk in chunks if chunk)


def build_queries(pages: list[Page], max_queries: int) -> list[str]:
    queries: list[str] = []
    source = source_text(pages).lower()
    anchors = []
    for phrase in [
        "feature flag release readiness",
        "feature flag audit stale flags",
        "feature flag rollback evidence",
        "feature flag compliance approval workflow",
        "release readiness certificate feature flags",
        "CAB release runbook feature flags",
        "LaunchDarkly release review audit rollback",
        "stale feature flag cleanup owner approver",
    ]:
        if any(word in source for word in phrase.split()[:2]):
            anchors.append(phrase)
    queries.extend(anchors)

    tokens = words(source_text(pages))
    phrase_counts = Counter(ngrams(tokens, 2) + ngrams(tokens, 3))
    for phrase, _count in phrase_counts.most_common(30):
        if len(phrase) >= 12 and any(marker in phrase for marker in ["flag", "release", "rollback", "audit", "compliance", "approver", "stale"]):
            queries.append(f"{phrase} feature flags release")

    cleaned: list[str] = []
    seen: set[str] = set()
    for query in queries:
        value = re.sub(r"\s+", " ", query).strip(" .,-")
        if len(value) < 8:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
        if len(cleaned) >= max_queries:
            break
    return cleaned


def tavily_search(api_key: str, query: str, max_results: int, exclude_domains: list[str]) -> list[dict]:
    response = requests.post(
        "https://api.tavily.com/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_favicon": True,
            "exclude_domains": exclude_domains,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("results", [])


def load_source_pages(source_url: str, feed_files: list[str], source_max_pages: int) -> list[Page]:
    pages: list[Page] = []
    for feed_file in feed_files:
        pages.extend(load_feed_file(Path(feed_file)))
    if not pages and source_url:
        pages = fetch_crawler_feed(source_url)
    if not pages and source_url:
        pages = crawl_site(source_url, source_max_pages, 0.75)
    return pages


def discover(args: argparse.Namespace) -> dict:
    load_dotenv()
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is required for discovery.")

    source_url = normalize_url(args.source_url)
    source_domain = root_domain(source_url)
    source_pages = load_source_pages(source_url, args.feed_file or [], args.source_max_pages)
    if not source_pages:
        raise RuntimeError(f"No source pages could be read from {source_url}")

    exclude_domains = sorted(set([source_domain, "www." + source_domain, *DEFAULT_EXCLUDE_DOMAINS, *(args.exclude_domain or [])]))
    queries = build_queries(source_pages, args.max_queries)
    discovered: dict[str, dict] = {}

    for query in queries:
        for result in tavily_search(api_key, query, args.results_per_query, exclude_domains):
            url = result.get("url")
            if not url:
                continue
            normalized = normalize_url(url)
            domain = root_domain(normalized)
            if domain in exclude_domains:
                continue
            if domain not in discovered or result.get("score", 0) > discovered[domain].get("score", 0):
                discovered[domain] = {
                    "domain": domain,
                    "url": normalized,
                    "title": result.get("title", ""),
                    "content": result.get("content", ""),
                    "score": result.get("score", 0),
                    "query": query,
                }

    ranked = sorted(discovered.values(), key=lambda item: item.get("score", 0), reverse=True)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(item["url"] for item in ranked[: args.max_domains]) + "\n", encoding="utf-8")

    results_path = Path(args.results_json)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(
            {
                "source_url": source_url,
                "source_pages": [asdict(page) for page in source_pages],
                "queries": queries,
                "discovered": ranked[: args.max_domains],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return {"queries": queries, "discovered": ranked[: args.max_domains], "output": str(output_path)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Discover related websites from a source website using Tavily Search.")
    parser.add_argument("--source-url", default="https://www.compassultra.com/")
    parser.add_argument("--feed-file", action="append", help="Optional local crawler feed JSON for the source site.")
    parser.add_argument("--exclude-domain", action="append", help="Additional domains to exclude.")
    parser.add_argument("--source-max-pages", type=int, default=5)
    parser.add_argument("--max-queries", type=int, default=8)
    parser.add_argument("--results-per-query", type=int, default=5)
    parser.add_argument("--max-domains", type=int, default=12)
    parser.add_argument("--output", default="targets/discovered_websites.txt")
    parser.add_argument("--results-json", default="targets/discovery_results.json")
    args = parser.parse_args(argv)

    result = discover(args)
    print(f"Wrote {len(result['discovered'])} discovered URLs to {result['output']}")
    for item in result["discovered"]:
        print(f"{item['domain']} <- {item['query']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
