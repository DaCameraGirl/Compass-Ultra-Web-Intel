from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_ops.settings import Settings
from data_ops.snowflake import connect, qualified_name, quote_ident


USER_AGENT = "CompassUltraWebsiteIntel/1.0 (+https://www.compassultra.com/)"


@dataclass(frozen=True)
class Page:
    url: str
    domain: str
    title: str
    meta_description: str
    headings: list[str]
    body_text: str
    status_code: int
    content_type: str
    content_hash: str
    fetched_at: datetime
    raw_payload: dict[str, Any]


def page_from_feed_item(item: dict[str, Any], fallback_site: str) -> Page:
    url = normalize_url(str(item.get("url") or fallback_site))
    title = text_or_empty(item.get("title"))
    meta_description = text_or_empty(item.get("meta_description") or item.get("description"))
    headings = [text_or_empty(value) for value in item.get("headings", []) if text_or_empty(value)]
    body_text = text_or_empty(item.get("body_text") or item.get("text") or item.get("content"))
    content = " ".join([title, meta_description, " ".join(headings), body_text])
    content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
    fetched_at = datetime.now(timezone.utc)
    return Page(
        url=url,
        domain=root_domain(url),
        title=title,
        meta_description=meta_description,
        headings=headings,
        body_text=body_text[:500_000],
        status_code=200,
        content_type="application/json+crawler-feed",
        content_hash=content_hash,
        fetched_at=fetched_at,
        raw_payload={
            "source": "crawler_feed",
            "fetched_at": fetched_at.isoformat(),
            "item": item,
        },
    )


def pages_from_feed(payload: dict[str, Any], fallback_site: str) -> list[Page]:
    site = str(payload.get("site") or fallback_site)
    items = payload.get("pages") or []
    if not isinstance(items, list):
        raise ValueError("crawler feed must contain a pages array")
    return [page_from_feed_item(item, site) for item in items if isinstance(item, dict)]


def load_feed_file(path: Path) -> list[Page]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pages_from_feed(payload, str(payload.get("site") or path.as_uri()))


def fetch_crawler_feed(start_url: str) -> list[Page]:
    parsed = urlparse(normalize_url(start_url))
    feed_url = f"{parsed.scheme}://{parsed.netloc}/crawler-feed.json"
    response = requests.get(
        feed_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=25,
    )
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    return pages_from_feed(payload, start_url)


def normalize_url(url: str) -> str:
    clean, _fragment = urldefrag(url.strip())
    parsed = urlparse(clean)
    if not parsed.scheme:
        clean = "https://" + clean
        parsed = urlparse(clean)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, fragment="", query=parsed.query).geturl()


def same_domain(url: str, root_domain: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == root_domain or host.endswith("." + root_domain)


def root_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def text_or_empty(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_page(url: str, response: requests.Response) -> tuple[Page, list[str]]:
    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "canvas", "form"]):
        tag.decompose()

    title = text_or_empty(soup.title.string if soup.title else "")
    description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = text_or_empty(description_tag.get("content") if description_tag else "")
    headings = [text_or_empty(tag.get_text(" ")) for tag in soup.find_all(["h1", "h2"]) if text_or_empty(tag.get_text(" "))]

    main = soup.find("main") or soup.body or soup
    body_text = text_or_empty(main.get_text(" "))
    body_text = body_text[:500_000]
    content_hash = hashlib.sha256(body_text.encode("utf-8", errors="ignore")).hexdigest()

    links = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = normalize_url(urljoin(url, href))
        if urlparse(absolute).scheme in {"http", "https"}:
            links.append(absolute)

    page = Page(
        url=url,
        domain=root_domain(url),
        title=title,
        meta_description=meta_description,
        headings=headings,
        body_text=body_text,
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
        content_hash=content_hash,
        fetched_at=datetime.now(timezone.utc),
        raw_payload={
            "url": url,
            "title": title,
            "meta_description": meta_description,
            "headings": headings,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "content_hash": content_hash,
        },
    )
    return page, links


def crawl_site(start_url: str, max_pages: int, delay_seconds: float) -> list[Page]:
    start = normalize_url(start_url)
    domain = root_domain(start)
    queue: deque[str] = deque([start])
    seen: set[str] = set()
    pages: list[Page] = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        if url in seen or not same_domain(url, domain):
            continue
        seen.add(url)
        try:
            response = session.get(url, timeout=25)
        except requests.RequestException:
            continue
        content_type = response.headers.get("content-type", "")
        if response.status_code >= 400 or "text/html" not in content_type:
            continue
        page, links = extract_page(url, response)
        pages.append(page)
        for link in links:
            if link not in seen and same_domain(link, domain):
                queue.append(link)
        time.sleep(delay_seconds)
    return pages


def create_web_objects(connection, settings: Settings) -> None:
    db = settings.snowflake_database
    schema = settings.snowflake_web_schema
    with connection.cursor() as cursor:
        cursor.execute(f"create database if not exists {quote_ident(db)}")
        cursor.execute(f"create schema if not exists {qualified_name(db, schema)}")
        cursor.execute(
            f"""
            create table if not exists {qualified_name(db, schema, 'PAGES')} (
                url varchar not null,
                domain varchar not null,
                title varchar,
                meta_description varchar,
                headings variant,
                body_text varchar,
                status_code number,
                content_type varchar,
                content_hash varchar,
                fetched_at timestamp_tz not null,
                raw_payload variant not null,
                primary key (url)
            )
            """
        )
        cursor.execute(f"use database {quote_ident(db)}")
        cursor.execute(f"use schema {qualified_name(db, schema)}")


def serialize(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def merge_pages(connection, settings: Settings, pages: list[Page]) -> None:
    if not pages:
        return
    table = qualified_name(settings.snowflake_database, settings.snowflake_web_schema, "PAGES")
    temp_table = f"TMP_WEB_PAGES_{uuid.uuid4().hex[:10].upper()}"
    columns = [
        "url",
        "domain",
        "title",
        "meta_description",
        "headings",
        "body_text",
        "status_code",
        "content_type",
        "content_hash",
        "fetched_at",
        "raw_payload",
    ]
    rows = []
    for page in pages:
        rows.append(
            (
                page.url,
                page.domain,
                page.title,
                page.meta_description,
                json.dumps(page.headings, sort_keys=True),
                page.body_text,
                str(page.status_code),
                page.content_type,
                page.content_hash,
                page.fetched_at.isoformat(),
                json.dumps(page.raw_payload, sort_keys=True),
            )
        )

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            create temporary table {quote_ident(temp_table)} (
                url varchar,
                domain varchar,
                title varchar,
                meta_description varchar,
                headings varchar,
                body_text varchar,
                status_code varchar,
                content_type varchar,
                content_hash varchar,
                fetched_at varchar,
                raw_payload varchar
            )
            """
        )
        cursor.executemany(
            f"""
            insert into {quote_ident(temp_table)}
            ({", ".join(columns)})
            values ({", ".join(["%s"] * len(columns))})
            """,
            rows,
        )
        cursor.execute(
            f"""
            merge into {table} as target
            using (
                select
                    url,
                    domain,
                    title,
                    meta_description,
                    parse_json(headings) as headings,
                    body_text,
                    try_to_number(status_code) as status_code,
                    content_type,
                    content_hash,
                    try_to_timestamp_tz(fetched_at) as fetched_at,
                    parse_json(raw_payload) as raw_payload
                from {quote_ident(temp_table)}
            ) as source
            on target.url = source.url
            when matched then update set
                domain = source.domain,
                title = source.title,
                meta_description = source.meta_description,
                headings = source.headings,
                body_text = source.body_text,
                status_code = source.status_code,
                content_type = source.content_type,
                content_hash = source.content_hash,
                fetched_at = source.fetched_at,
                raw_payload = source.raw_payload
            when not matched then insert
                (url, domain, title, meta_description, headings, body_text, status_code,
                 content_type, content_hash, fetched_at, raw_payload)
            values
                (source.url, source.domain, source.title, source.meta_description, source.headings,
                 source.body_text, source.status_code, source.content_type, source.content_hash,
                 source.fetched_at, source.raw_payload)
            """
        )


def read_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.url or [])
    if args.urls_file and not args.skip_urls_file:
        path = Path(args.urls_file)
        urls.extend(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return [normalize_url(url) for url in urls]


def require_snowflake(settings: Settings) -> None:
    missing = [
        name
        for name, value in {
            "SNOWFLAKE_ACCOUNT": settings.snowflake_account,
            "SNOWFLAKE_USER": settings.snowflake_user,
            "SNOWFLAKE_ROLE": settings.snowflake_role,
            "SNOWFLAKE_WAREHOUSE": settings.snowflake_warehouse,
        }.items()
        if not value
    ]
    if (
        not settings.snowflake_password
        and not settings.snowflake_private_key_path
        and settings.snowflake_authenticator.lower() != "externalbrowser"
    ):
        missing.append("SNOWFLAKE_PASSWORD, SNOWFLAKE_PRIVATE_KEY_PATH, or SNOWFLAKE_AUTHENTICATOR=externalbrowser")
    if missing:
        raise RuntimeError("Missing required Snowflake configuration: " + ", ".join(missing))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Crawl real websites into Snowflake for Compass Ultra website intelligence.")
    parser.add_argument("--url", action="append", help="Website URL to crawl. Can be repeated.")
    parser.add_argument("--urls-file", default="targets/market_websites.txt", help="File containing one URL per line.")
    parser.add_argument("--skip-urls-file", action="store_true", help="Only use explicit --url and --feed-file inputs.")
    parser.add_argument("--feed-file", action="append", help="Crawler feed JSON file to load. Can be repeated.")
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("WEB_CRAWL_MAX_PAGES", "25")))
    parser.add_argument("--delay-seconds", type=float, default=0.75)
    parser.add_argument("--bootstrap-only", action="store_true")
    args = parser.parse_args(argv)

    load_dotenv()
    settings = Settings.from_env()
    require_snowflake(settings)

    with connect(settings) as snowflake_connection:
        create_web_objects(snowflake_connection, settings)
        if args.bootstrap_only:
            print("Website intelligence raw Snowflake objects are ready.")
            return 0

        total_pages = 0
        for feed_file in args.feed_file or []:
            pages = load_feed_file(Path(feed_file))
            merge_pages(snowflake_connection, settings, pages)
            total_pages += len(pages)
            print(f"{feed_file}: loaded {len(pages)} feed pages")

        urls = read_urls(args)
        if not urls:
            if total_pages:
                print(f"Loaded {total_pages} pages into Snowflake.")
                return 0
            raise RuntimeError("No URLs or feed files supplied.")

        for url in urls:
            pages = fetch_crawler_feed(url)
            if pages:
                print(f"{url}: loaded {len(pages)} crawler-feed pages")
            else:
                pages = crawl_site(url, args.max_pages, args.delay_seconds)
                print(f"{url}: loaded {len(pages)} pages")
            merge_pages(snowflake_connection, settings, pages)
            total_pages += len(pages)
        print(f"Loaded {total_pages} pages into Snowflake.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
