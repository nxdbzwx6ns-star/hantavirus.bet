#!/usr/bin/env python3
"""
HantaVirus.info — News Scraper
Fetches RSS feeds from authoritative health/news sources,
filters for hantavirus-relevant content, outputs news.json.

Run:  python scraper.py
Schedule: GitHub Actions (see .github/workflows/scrape.yml)
"""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── CONFIGURATION ────────────────────────────────────────────────────

OUTPUT_FILE = Path(__file__).parent / "news.json"
MAX_ARTICLES = 50          # keep newest N articles total
REQUEST_TIMEOUT = 15       # seconds per feed
USER_AGENT = (
    "Mozilla/5.0 (compatible; HantaVirusInfoBot/1.0; "
    "+https://hantavirus.info)"
)

# Keywords used to filter articles
KEYWORDS = [
    "hantavirus", "hantaviral", "hanta virus",
    "sin nombre", "andes virus", "puumala", "hantaan",
    "dobrava", "seoul virus",
    "HPS", "HFRS",
    "hemorrhagic fever renal syndrome",
    "hantavirus pulmonary syndrome",
    "rodent-borne virus", "deer mouse virus",
]

KEYWORD_RE = re.compile(
    "|".join(re.escape(k) for k in KEYWORDS),
    re.IGNORECASE
)

# ── NEWS SOURCES ─────────────────────────────────────────────────────
#
# All sources are authoritative public-health or major news outlets.
# Google News RSS is used for broad coverage; no scraping of paywalled content.

FEEDS = [
    # WHO Disease Outbreak News
    {
        "name": "WHO",
        "url": "https://www.who.int/rss-feeds/news-releases-en.xml",
        "always_include": False,
    },
    # CDC Newsroom
    {
        "name": "CDC",
        "url": "https://tools.cdc.gov/api/v2/resources/media/316422.rss",
        "always_include": False,
    },
    # ProMED-mail (gold standard for outbreak surveillance)
    {
        "name": "ProMED",
        "url": "https://promedmail.org/feed/",
        "always_include": False,
    },
    # Reuters Health
    {
        "name": "Reuters Health",
        "url": "https://feeds.reuters.com/reuters/healthNews",
        "always_include": False,
    },
    # Google News — hantavirus (broad, catches regional outlets)
    {
        "name": "Google News",
        "url": (
            "https://news.google.com/rss/search"
            "?q=hantavirus&hl=en-US&gl=US&ceid=US:en"
        ),
        "always_include": True,   # already filtered by query
    },
    # PAHO (Pan American Health Organization)
    {
        "name": "PAHO",
        "url": "https://www.paho.org/en/rss.xml",
        "always_include": False,
    },
    # Nature News (scientific coverage)
    {
        "name": "Nature",
        "url": "https://www.nature.com/subjects/emerging-infectious-diseases.rss",
        "always_include": False,
    },
    # AP Health
    {
        "name": "AP Health",
        "url": "https://rsshub.app/apnews/topics/health",
        "always_include": False,
    },
    # BBC Health
    {
        "name": "BBC Health",
        "url": "https://feeds.bbci.co.uk/news/health/rss.xml",
        "always_include": False,
    },
]

# ── HELPERS ──────────────────────────────────────────────────────────

def fetch_feed(url: str, timeout: int = REQUEST_TIMEOUT) -> bytes | None:
    """Fetch a URL, return bytes or None on failure."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (URLError, HTTPError, Exception) as exc:
        print(f"  ✗ Fetch error for {url[:60]}…: {exc}", file=sys.stderr)
        return None


def strip_tags(text: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_date(raw: str) -> str | None:
    """Try to parse an RSS date string into ISO-8601."""
    if not raw:
        return None
    # RFC 2822 format common in RSS
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    raw = raw.strip()
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def is_relevant(title: str, description: str, always_include: bool) -> bool:
    """Return True if article appears relevant to hantavirus."""
    if always_include:
        return True
    combined = (title or "") + " " + (description or "")
    return bool(KEYWORD_RE.search(combined))


def parse_rss(xml_bytes: bytes, source_name: str, always_include: bool) -> list[dict]:
    """Parse RSS/Atom XML, return list of article dicts."""
    articles = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        print(f"  ✗ XML parse error in {source_name}: {exc}", file=sys.stderr)
        return []

    # Namespace handling
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc":   "http://purl.org/dc/elements/1.1/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    # Try RSS 2.0 items
    items = root.findall(".//item")
    # Try Atom entries if no items
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for item in items:
        def text(tag, alt_tag=None):
            el = item.find(tag)
            if el is None and alt_tag:
                el = item.find(alt_tag)
            return (el.text or "").strip() if el is not None else ""

        # RSS 2.0
        title = (
            text("title") or
            text("{http://www.w3.org/2005/Atom}title")
        )
        link = (
            text("link") or
            text("{http://www.w3.org/2005/Atom}link") or
            (item.find("{http://www.w3.org/2005/Atom}link") or ET.Element("x")).get("href", "")
        )
        description = strip_tags(
            text("description") or
            text("{http://www.w3.org/2005/Atom}summary") or
            text("{http://www.w3.org/2005/Atom}content") or
            text("{http://purl.org/rss/1.0/modules/content/}encoded")
        )
        pub_date = (
            text("pubDate") or
            text("{http://www.w3.org/2005/Atom}published") or
            text("{http://www.w3.org/2005/Atom}updated") or
            text("{http://purl.org/dc/elements/1.1/}date")
        )

        if not title and not link:
            continue

        if not is_relevant(title, description, always_include):
            continue

        articles.append({
            "title":       title,
            "link":        link,
            "description": description[:400] if description else "",
            "source":      source_name,
            "date":        parse_date(pub_date),
            "raw_date":    pub_date,
        })

    return articles


def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by link (keep first occurrence)."""
    seen_links = set()
    seen_titles = set()
    unique = []
    for a in articles:
        link  = a.get("link", "").strip()
        title = a.get("title", "").strip().lower()
        if link and link in seen_links:
            continue
        if title and title in seen_titles:
            continue
        if link:
            seen_links.add(link)
        if title:
            seen_titles.add(title)
        unique.append(a)
    return unique


def sort_articles(articles: list[dict]) -> list[dict]:
    """Sort articles: newest first. Articles without date go last."""
    def sort_key(a):
        d = a.get("date")
        return d if d else "0000"
    return sorted(articles, key=sort_key, reverse=True)


# ── MAIN ─────────────────────────────────────────────────────────────

def scrape() -> None:
    print(f"\n{'='*60}")
    print(f"HantaVirus.info Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}\n")

    all_articles: list[dict] = []

    for feed in FEEDS:
        name  = feed["name"]
        url   = feed["url"]
        always = feed.get("always_include", False)
        print(f"  → Fetching {name} …")

        raw = fetch_feed(url)
        if raw is None:
            continue

        articles = parse_rss(raw, name, always)
        print(f"     Found {len(articles)} relevant articles")
        all_articles.extend(articles)
        time.sleep(0.5)  # be polite

    # Deduplicate, sort, trim
    all_articles = deduplicate(all_articles)
    all_articles = sort_articles(all_articles)
    all_articles = all_articles[:MAX_ARTICLES]

    output = {
        "updated":       datetime.now(timezone.utc).isoformat(),
        "total":         len(all_articles),
        "sources":       list({a["source"] for a in all_articles}),
        "articles":      all_articles,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n✓ Saved {len(all_articles)} articles → {OUTPUT_FILE}")
    print(f"  Sources: {', '.join(output['sources'])}")


if __name__ == "__main__":
    scrape()
