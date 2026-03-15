#!/usr/bin/env python3
"""
Marketing Hub RSS Fetcher
Fetches articles from multiple RSS feeds, extracts full content, and generates JSON output.
Uses only Python standard library - no external dependencies.
"""

import json
import re
import urllib.request
import urllib.error
from datetime import datetime
from html.parser import HTMLParser
from html import unescape
from pathlib import Path


class ContentExtractor(HTMLParser):
    """Extract main content from HTML - looks for article/main containers and known class patterns"""
    def __init__(self):
        super().__init__()
        self.content_blocks = []
        self.current_text = []
        self.depth = 0
        self.in_content = False
        self.content_depth = 0
        self.skip_depth = 0
        self.in_skip = False
        self.skip_tags = {'script', 'style', 'nav', 'header', 'footer', 'aside',
                          'form', 'button', 'noscript', 'figcaption', 'iframe'}
        self.content_tags = {'article', 'main'}
        self.content_classes = {
            'article-content', 'article-body', 'post-content', 'post-body',
            'entry-content', 'article__body', 'story-body', 'article-text',
            'content-body', 'article__content', 'main-content',
        }

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        attr_dict = dict(attrs)
        classes = attr_dict.get('class', '') or ''

        if self.in_skip:
            self.skip_depth += 1
            return

        if tag in self.skip_tags:
            self.in_skip = True
            self.skip_depth = 1
            return

        if not self.in_content:
            if tag in self.content_tags:
                self.in_content = True
                self.content_depth = self.depth
                return
            # Check for known content class patterns
            for cls in self.content_classes:
                if cls in classes.lower():
                    self.in_content = True
                    self.content_depth = self.depth
                    return

    def handle_endtag(self, tag):
        if self.in_skip:
            self.skip_depth -= 1
            if self.skip_depth <= 0:
                self.in_skip = False
                self.skip_depth = 0
            return

        if self.in_content and self.depth <= self.content_depth:
            # Flush current text block
            if self.current_text:
                text = ' '.join(self.current_text).strip()
                if len(text) > 20:
                    self.content_blocks.append(text)
                self.current_text = []
            self.in_content = False

        if tag in ('p', 'h2', 'h3', 'h4', 'li', 'blockquote'):
            if self.current_text:
                text = ' '.join(self.current_text).strip()
                if len(text) > 20:
                    self.content_blocks.append(text)
                self.current_text = []

        self.depth -= 1

    def handle_data(self, data):
        if self.in_content and not self.in_skip:
            text = data.strip()
            if text:
                self.current_text.append(text)

    def get_text(self):
        blocks = self.content_blocks[:]
        if self.current_text:
            text = ' '.join(self.current_text).strip()
            if len(text) > 20:
                blocks.append(text)
        return '\n\n'.join(blocks)


def fetch_url(url, timeout=10):
    """Safely fetch URL content"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception:
        return None


def extract_og_image(html):
    """Extract best available image from HTML meta tags"""
    if not html:
        return None
    patterns = [
        r'<meta\s+property=["\']og:image:secure_url["\']\s+content=["\'](https?://[^"\']+)["\']',
        r'<meta\s+property=["\']og:image["\']\s+content=["\'](https?://[^"\']+)["\)]',
        r'<meta\s+content=["\'](https?://[^"\']+)["\']\s+property=["\']og:image["\']',
        r'<meta\s+name=["\']twitter:image["\']\s+content=["\'](https?://[^"\']+)["\']',
        r'<meta\s+content=["\'](https?://[^"\']+)["\']\s+name=["\']twitter:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            url = match.group(1).strip()
            if url and not url.endswith(('.gif', '.svg', '.ico')):
                return url
    return None


def extract_image_from_content(html):
    """Extract first meaningful image from HTML content"""
    if not html:
        return None
    # Skip tiny tracking pixels, icons
    matches = re.finditer(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html, re.IGNORECASE)
    for m in matches:
        url = m.group(1)
        if any(skip in url.lower() for skip in ['pixel', 'tracking', 'icon', 'logo', '1x1', 'spacer']):
            continue
        if not url.endswith(('.gif', '.svg', '.ico', '.png')):
            return url
        if url.endswith('.png'):
            # Accept larger PNG images
            width_m = re.search(r'width=["\'](\d+)["\']', m.group(0))
            if width_m and int(width_m.group(1)) > 100:
                return url
    return None


def fetch_full_article(url, timeout=12):
    """Fetch and extract full article content from a URL"""
    html = fetch_url(url, timeout=timeout)
    if not html:
        return None, None

    # Extract image first
    image = extract_og_image(html)

    # Extract content using the ContentExtractor
    extractor = ContentExtractor()
    try:
        extractor.feed(html)
        content = extractor.get_text()
    except Exception:
        content = None

    # Fall back to simple paragraph extraction if ContentExtractor got nothing
    if not content or len(content) < 200:
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        texts = []
        for p in paras:
            text = re.sub(r'<[^>]+>', '', p).strip()
            if len(text) > 60:
                texts.append(text)
        content = '\n\n'.join(texts[:20]) if texts else None

    return image, content


def sanitize_html(html, max_length=8000):
    """Keep only safe HTML tags, remove clutter, limit length"""
    if not html:
        return ""

    allowed_tags = [
        'p', 'h2', 'h3', 'h4', 'h5', 'h6',
        'strong', 'b', 'em', 'i', 'u',
        'a', 'ul', 'ol', 'li', 'blockquote',
        'img', 'br', 'figure', 'figcaption',
    ]

    # Remove scripts, styles, nav, header, footer, ads, forms
    for tag in ['script', 'style', 'nav', 'header', 'footer', 'aside',
                'form', 'button', 'noscript', 'iframe', 'ins', 'figure.wp-caption']:
        html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove disallowed tags but keep their text content
    all_found_tags = set(re.findall(r'</?([a-z][a-z0-9]*)', html, re.IGNORECASE))
    for tag in all_found_tags:
        if tag.lower() not in allowed_tags:
            html = re.sub(rf'</?{re.escape(tag)}[^>]*>', ' ', html, flags=re.IGNORECASE)

    # Remove dangerous attributes (keep href and src)
    html = re.sub(r'\s(on\w+)=["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
    html = re.sub(r'\s(on\w+)=[^\s>]+', '', html, flags=re.IGNORECASE)
    html = re.sub(r'href=["\']javascript:[^"\']*["\']', 'href="#"', html, flags=re.IGNORECASE)

    # Clean up whitespace
    html = re.sub(r'\n\s*\n\s*\n', '\n\n', html)
    html = re.sub(r'<p>\s*</p>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<br\s*/?>\s*<br\s*/?>', '</p><p>', html, flags=re.IGNORECASE)

    # Truncate
    if len(html) > max_length:
        html = html[:max_length] + '...'

    return html.strip()


def extract_summary(text, sentences=4):
    """Extract a coherent summary of n sentences from plain text"""
    if not text:
        return ""
    # Split on sentence boundaries
    text = re.sub(r'\s+', ' ', text).strip()
    parts = re.split(r'(?<=[.!?])\s+', text)
    result = []
    for part in parts:
        part = part.strip()
        if len(part) > 40:
            result.append(part)
        if len(result) >= sentences:
            break
    return ' '.join(result)


def parse_date(date_string):
    """Parse RSS date to ISO format"""
    if not date_string:
        return datetime.now().isoformat() + 'Z'

    date_string = date_string.strip()

    date_formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S GMT',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_string, fmt)
            return dt.isoformat() + 'Z'
        except ValueError:
            continue

    return datetime.now().isoformat() + 'Z'


def extract_rss_content(feed_xml):
    """Parse RSS/Atom feed and return raw article dicts"""
    articles = []

    items = re.findall(r'<item[^>]*>.*?</item>', feed_xml, re.DOTALL | re.IGNORECASE)
    if not items:
        items = re.findall(r'<entry[^>]*>.*?</entry>', feed_xml, re.DOTALL | re.IGNORECASE)

    for item in items:
        try:
            article = {}

            # Title
            title_match = re.search(
                r'<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>',
                item, re.DOTALL | re.IGNORECASE)
            article['title'] = unescape(
                re.sub(r'<[^>]+>', '', title_match.group(1).strip())
            ) if title_match else 'Untitled'

            # Link
            link_match = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', item, re.IGNORECASE)
            if not link_match:
                link_match = re.search(r'<link[^>]*>(https?://[^\s<]+)', item, re.IGNORECASE)
            article['link'] = unescape(link_match.group(1).strip()) if link_match else ''

            # Full content: try content:encoded, content, then description
            full_content = ''
            for pattern in [
                r'<content:encoded[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</content:encoded>',
                r'<content[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</content[^>]*>',
            ]:
                m = re.search(pattern, item, re.DOTALL | re.IGNORECASE)
                if m:
                    full_content = m.group(1).strip()
                    break

            desc_match = re.search(
                r'<description[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>',
                item, re.DOTALL | re.IGNORECASE)
            description_raw = unescape(desc_match.group(1).strip()) if desc_match else ''

            if not full_content:
                full_content = description_raw

            article['fullContent'] = sanitize_html(full_content)

            # Plain text description (for search + summary)
            plain = re.sub(r'<[^>]+>', ' ', full_content)
            plain = re.sub(r'\s+', ' ', plain).strip()
            article['description'] = plain[:300] if plain else ''

            # Publication date
            for dpat in [r'<pubDate[^>]*>(.*?)</pubDate>',
                         r'<published[^>]*>(.*?)</published>',
                         r'<updated[^>]*>(.*?)</updated>']:
                dm = re.search(dpat, item, re.DOTALL | re.IGNORECASE)
                if dm:
                    article['pubDate'] = parse_date(dm.group(1).strip())
                    break
            else:
                article['pubDate'] = parse_date(None)

            # Image: media:content, media:thumbnail, enclosure, inline img
            image = None
            for img_pat in [
                r'<media:content[^>]+url=["\']([^"\']+\.(jpe?g|png|webp))["\']',
                r'<media:thumbnail[^>]+url=["\']([^"\']+)["\']',
                r'<enclosure[^>]+url=["\']([^"\']+)["\'][^>]+type=["\']image/',
                r'<enclosure[^>]+type=["\']image/[^"\']+["\'][^>]+url=["\']([^"\']+)["\']',
            ]:
                m = re.search(img_pat, item, re.IGNORECASE)
                if m:
                    image = m.group(1)
                    break

            if not image:
                image = extract_image_from_content(full_content)

            article['image'] = image if image and image.startswith('http') and not image.endswith('.gif') else None

            articles.append(article)
        except Exception:
            continue

    return articles


def categorize_article(title, description):
    """Categorize article based on content keywords"""
    content = (title + ' ' + description).lower()

    rules = {
        'social': ['social media', 'instagram', 'facebook', 'twitter', 'x.com',
                   'linkedin', 'tiktok', 'youtube', 'pinterest', 'snapchat',
                   'influencer', 'creator', 'followers', 'engagement'],
        'branding': ['brand', 'branding', 'identity', 'logo', 'rebranding',
                     'brand awareness', 'brand strategy', 'brand voice',
                     'reputation', 'visual identity'],
        'content': ['content marketing', 'content strategy', 'blog', 'copywriting',
                    'storytelling', 'editorial', 'content creation', 'newsletter',
                    'podcast', 'video content', 'writing'],
        'strategy': ['marketing strategy', 'campaign', 'roi', 'analytics', 'data',
                     'metrics', 'conversion', 'funnel', 'b2b', 'b2c', 'growth',
                     'planning', 'market research', 'competitive'],
        'digital': ['digital', 'seo', 'sem', 'ppc', 'email marketing', 'automation',
                    'ai marketing', 'martech', 'google ads', 'programmatic',
                    'display advertising', 'performance marketing', 'cro'],
    }

    for category, keywords in rules.items():
        if any(kw in content for kw in keywords):
            return category

    return 'digital'


def calculate_reading_time(text):
    """Estimate reading time in minutes (avg 200 words/min)"""
    words = len(text.split())
    return max(1, round(words / 200))


def fetch_feeds():
    """Fetch all RSS feeds and process articles"""
    feeds = [
        {'url': 'https://blog.hubspot.com/marketing/rss.xml', 'source': 'HubSpot Blog'},
        {'url': 'https://contentmarketinginstitute.com/feed/', 'source': 'Content Marketing Institute'},
        {'url': 'https://www.socialmediatoday.com/feed/', 'source': 'Social Media Today'},
        {'url': 'https://www.searchenginejournal.com/feed/', 'source': 'Search Engine Journal'},
        {'url': 'https://www.marketingweek.com/feed/', 'source': 'Marketing Week'},
        {'url': 'https://www.adweek.com/feed/', 'source': 'Adweek'},
        {'url': 'https://moz.com/blog/feed', 'source': 'Moz'},
        {'url': 'https://www.socialmediaexaminer.com/feed/', 'source': 'Social Media Examiner'},
        {'url': 'https://blog.hootsuite.com/feed/', 'source': 'Hootsuite Blog'},
        {'url': 'https://sproutsocial.com/insights/feed/', 'source': 'Sprout Social'},
        {'url': 'https://www.thinkwithgoogle.com/rss/', 'source': 'Think with Google'},
        {'url': 'https://neilpatel.com/blog/feed/', 'source': 'Neil Patel'},
    ]

    all_articles = []
    sources_seen = set()

    for feed_config in feeds:
        try:
            print(f"Fetching {feed_config['source']}...")
            feed_xml = fetch_url(feed_config['url'], timeout=15)
            if not feed_xml:
                print(f"  -> Failed to fetch feed")
                continue

            articles = extract_rss_content(feed_xml)
            print(f"  -> Found {len(articles)} articles in feed")

            for article in articles[:12]:  # Max 12 per feed
                article['source'] = feed_config['source']
                article['category'] = categorize_article(article['title'], article['description'])

                # Try og:image and full content fetch if needed
                needs_image = not article.get('image')
                needs_content = len(article.get('fullContent', '')) < 400

                if (needs_image or needs_content) and article.get('link'):
                    try:
                        og_img, fetched_content = fetch_full_article(article['link'], timeout=10)
                        if needs_image and og_img:
                            article['image'] = og_img
                        if needs_content and fetched_content and len(fetched_content) > len(article.get('fullContent', '')):
                            # Store as plain text paragraphs wrapped in <p> tags
                            paragraphs = [p.strip() for p in fetched_content.split('\n\n') if len(p.strip()) > 40]
                            article['fullContent'] = '\n'.join(f'<p>{p}</p>' for p in paragraphs[:30])
                    except Exception:
                        pass

                # Build summary from available content
                plain_content = re.sub(r'<[^>]+>', ' ', article.get('fullContent', ''))
                plain_content = re.sub(r'\s+', ' ', plain_content).strip()

                if not article.get('description') or len(article['description']) < 100:
                    article['description'] = extract_summary(plain_content, sentences=3)

                article['summary'] = extract_summary(plain_content, sentences=5)
                article['readingTime'] = calculate_reading_time(plain_content)

                sources_seen.add(feed_config['source'])
                all_articles.append(article)

        except Exception as e:
            print(f"  -> Error processing feed: {e}")
            continue

    # Sort by date descending
    all_articles.sort(key=lambda x: x.get('pubDate', ''), reverse=True)

    # Deduplicate by title
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = re.sub(r'\s+', ' ', article['title'].lower().strip())
        if title_key not in seen_titles and article.get('link'):
            unique_articles.append(article)
            seen_titles.add(title_key)

    print(f"\nTotal: {len(unique_articles)} unique articles from {len(sources_seen)} sources")
    return unique_articles[:100], sorted(sources_seen)


def main():
    """Main entry point"""
    articles, sources = fetch_feeds()

    output_data = {
        'updated': datetime.now().isoformat() + 'Z',
        'total': len(articles),
        'sources': sources,
        'articles': articles,
    }

    output_path = Path(__file__).parent.parent / 'data' / 'news.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f'\nOutput saved to {output_path}')
    print(f'{len(articles)} articles, {len(sources)} sources')


if __name__ == '__main__':
    main()
