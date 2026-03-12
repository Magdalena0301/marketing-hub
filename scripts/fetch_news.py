#!/usr/bin/env python3
"""
Marketing Hub â RSS Feed Fetcher
Fetches marketing news from multiple RSS feeds, extracts images,
and generates a JSON file for the static GitHub Pages site.
Runs daily via GitHub Actions.
"""

import json
import re
import html
import os
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
from xml.etree import ElementTree as ET

# ââââ RSS FEED SOURCES ââââ
FEEDS = [
    {"url": "https://blog.hubspot.com/marketing/rss.xml", "source": "HubSpot Blog"},
    {"url": "https://contentmarketinginstitute.com/feed/", "source": "Content Marketing Institute"},
    {"url": "https://www.socialmediatoday.com/feed/", "source": "Social Media Today"},
    {"url": "https://www.searchenginejournal.com/feed/", "source": "Search Engine Journal"},
    {"url": "https://www.marketingweek.com/feed/", "source": "Marketing Week"},
    {"url": "https://www.adweek.com/feed/", "source": "Adweek"},
    {"url": "https://www.thinkwithgoogle.com/intl/en-gb/feed.xml", "source": "Think with Google"},
    {"url": "https://neilpatel.com/blog/feed/", "source": "Neil Patel"},
    {"url": "https://moz.com/devblog/feed", "source": "Moz"},
    {"url": "https://www.socialmediaexaminer.com/feed/", "source": "Social Media Examiner"},
]

# ââââ CATEGORY KEYWORDS ââââ
CATEGORIES = {
    "digital": ["seo", "ppc", "google ads", "analytics", "sem", "search engine",
                "paid media", "performance marketing", "email marketing",
                "automation", "adtech", "programmatic", "digital marketing",
                "martech", "crm", "wordpress"],
    "social":  ["instagram", "tiktok", "facebook", "linkedin", "twitter",
                "social media", "influencer", "creator economy", "reels",
                "youtube", "snapchat", "threads", "pinterest", "social commerce",
                "ugc", "community"],
    "branding": ["brand", "branding", "rebrand", "logo", "identity", "campaign",
                 "awareness", "launch", "commercial", "advertising", "ad campaign",
                 "creative", "agency"],
    "content":  ["content marketing", "storytelling", "blog", "video marketing",
                 "podcast", "newsletter", "copywriting", "editorial", "cms",
                 "content strategy", "content creation"],
    "strategy": ["strategy", "market research", "consumer", "trend", "study",
                 "report", "forecast", "roi", "budget", "planning", "insight",
                 "data-driven", "b2b", "b2c", "retention", "growth", "ai marketing"]
}

# Common media namespaces in RSS
MEDIA_NS = {
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def clean_html(raw_html):
    """Remove HTML tags and decode entities."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", "", raw_html)
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:500]


def extract_image_from_html(html_str):
    """Try to find an image URL in HTML content."""
    if not html_str:
        return None
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_str)
    if match:
        url = match.group(1)
        if url.startswith("http") and not url.endswith(".gif"):
            return url
    return None


def extract_image(item):
    """Extract image URL from various RSS elements."""
    # 1. media:thumbnail
    thumb = item.find("media:thumbnail", MEDIA_NS)
    if thumb is not None:
        url = thumb.get("url")
        if url:
            return url

    # 2. media:content
    media = item.find("media:content", MEDIA_NS)
    if media is not None:
        url = media.get("url", "")
        if "image" in media.get("medium", "image") or "image" in media.get("type", ""):
            return url
        if url and any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            return url

    # 3. enclosure
    enc = item.find("enclosure")
    if enc is not None:
        enc_type = enc.get("type", "")
        if "image" in enc_type:
            return enc.get("url")

    # 4. Look in content:encoded for first <img>
    content_encoded = item.findtext("content:encoded", "", MEDIA_NS)
    img = extract_image_from_html(content_encoded)
    if img:
        return img

    # 5. Look in description for <img>
    desc = item.findtext("description", "")
    img = extract_image_from_html(desc)
    if img:
        return img

    return None


def categorize(text):
    """Assign a category based on keyword matching."""
    lower = text.lower()
    scores = {}
    for cat, keywords in CATEGORIES.items():
        scores[cat] = sum(1 for kw in keywords if kw in lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "digital"


def parse_date(date_str):
    """Try to parse various RSS date formats."""
    if not date_str:
        return datetime.now(timezone.utc)
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    # Handle timezone offset without colon (e.g. +0000)
    cleaned = date_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except (ValueError, AttributeError):
            continue
    return datetime.now(timezone.utc)


def fetch_feed(feed_info):
    """Fetch and parse a single RSS feed."""
    articles = []
    try:
        req = Request(feed_info["url"], headers={
            "User-Agent": "MarketingHub/1.0 (GitHub Pages)"
        })
        with urlopen(req, timeout=15) as response:
            data = response.read()

        root = ET.fromstring(data)

        # RSS 2.0
        items = root.findall(".//item")
        if items:
            for item in items[:12]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc_raw = item.findtext("description", "")
                desc = clean_html(desc_raw)
                pub_date = item.findtext("pubDate", "")
                image = extract_image(item)

                if not title:
                    continue

                category = categorize(title + " " + desc)

                articles.append({
                    "title": html.unescape(title),
                    "link": link,
                    "description": desc,
                    "source": feed_info["source"],
                    "pubDate": parse_date(pub_date).isoformat(),
                    "category": category,
                    "image": image,
                })

        # Atom
        else:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            for entry in entries[:12]:
                title = entry.findtext("atom:title", "", ns).strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                summary = clean_html(entry.findtext("atom:summary", "", ns))
                updated = entry.findtext("atom:updated", "", ns)

                # Try media:thumbnail in Atom
                thumb = entry.find("media:thumbnail", MEDIA_NS)
                image = thumb.get("url") if thumb is not None else None

                if not title:
                    continue

                category = categorize(title + " " + summary)

                articles.append({
                    "title": html.unescape(title),
                    "link": link,
                    "description": summary,
                    "source": feed_info["source"],
                    "pubDate": parse_date(updated).isoformat(),
                    "category": category,
                    "image": image,
                })

        print(f"  [OK] {feed_info['source']}: {len(articles)} articles")

    except Exception as e:
        print(f"  [WARN] {feed_info['source']}: {e}")

    return articles


def main():
    print("Marketing Hub â Fetching news...")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Feeds: {len(FEEDS)}\n")

    all_articles = []
    for feed in FEEDS:
        articles = fetch_feed(feed)
        all_articles.extend(articles)

    # Sort by date (newest first)
    all_articles.sort(key=lambda a: a["pubDate"], reverse=True)

    # Limit to most recent 60
    all_articles = all_articles[:60]

    # Stats
    with_images = sum(1 for a in all_articles if a.get("image"))
    print(f"\n  Total: {len(all_articles)} articles")
    print(f"  With images: {with_images}")

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "total": len(all_articles),
        "sources": list(set(a["source"] for a in all_articles)),
        "articles": all_articles,
    }

    os.makedirs("data", exist_ok=True)

    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  Saved to data/news.json")


if __name__ == "__main__":
    main()
