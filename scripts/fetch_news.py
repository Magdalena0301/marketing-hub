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
    """Extract main content from HTML"""
    def __init__(self):
        super().__init__()
        self.content = []
        self.in_article = False
        self.in_main = False
        self.in_text = False
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        self.tag_stack.append(tag)
        if tag in ('article', 'main', 'content'):
            self.in_article = True
            self.in_main = True
        elif tag in ('p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div'):
            if self.in_main:
                self.in_text = True

    def handle_endtag(self, tag):
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()
        if tag in ('article', 'main', 'content'):
            self.in_main = False

    def handle_data(self, data):
        if self.in_main and self.in_text:
            text = data.strip()
            if text and len(text) > 10:
                self.content.append(text)

    def get_text(self):
        return ' '.join(self.content)


def fetch_url(url, timeout=10):
    """Safely fetch URL content"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode('utf-8', errors='ignore')
    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        return None


def extract_og_image(html):
    """Extract Open Graph image from HTML"""
    match = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
    return match.group(1) if match else None


def extract_image_from_article(content):
    """Extract first image from article content"""
    match = re.search(r'<img[^>]+src=["\'](.*?)["\']', content, re.IGNORECASE)
    return match.group(1) if match else None


def sanitize_html(html, max_length=5000):
    """Keep only safe HTML tags and limit length"""
    if not html:
        return ""
    
    allowed_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'a', 'ul', 'ol', 'li', 'blockquote', 'img', 'br']
    
    # Remove script and style tags completely
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<iframe[^>]*>.*?</iframe>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove disallowed tags but keep content
    for tag in re.findall(r'</?([a-z][a-z0-9]*)', html, re.IGNORECASE):
        if tag.lower() not in allowed_tags:
            html = re.sub(f'</?{tag}[^>]*>', '', html, flags=re.IGNORECASE)
    
    # Remove dangerous attributes
    html = re.sub(r'\s(on\w+)=["\']*[^\s>"\']*["\']*', '', html, flags=re.IGNORECASE)
    html = re.sub(r'\s(javascript:)', '', html, flags=re.IGNORECASE)
    
    # Truncate if needed
    if len(html) > max_length:
        html = html[:max_length] + '...'
    
    return html.strip()


def parse_date(date_string):
    """Parse RSS date to ISO format"""
    if not date_string:
        return datetime.now().isoformat() + 'Z'
    
    date_formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S%z',
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_string.replace(' +0000', ' +0000'), fmt)
            return dt.isoformat() + 'Z'
        except ValueError:
            continue
    
    return datetime.now().isoformat() + 'Z'


def extract_rss_content(feed_xml):
    """Parse RSS/Atom feed"""
    articles = []

    # Extract items (RSS uses <item>, Atom uses <entry>)
    items = re.findall(r'<item[^>]*>.*?</item>', feed_xml, re.DOTALL | re.IGNORECASE)
    if not items:
        items = re.findall(r'<entry[^>]*>.*?</entry>', feed_xml, re.DOTALL | re.IGNORECASE)

    for item in items:
        try:
            article = {}

            # Extract title (handle CDATA)
            title_match = re.search(r'<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL | re.IGNORECASE)
            article['title'] = unescape(re.sub(r'<[^>]+>', '', title_match.group(1).strip())) if title_match else 'Untitled'

            # Extract link (RSS: <link>url</link>, Atom: <link href="url"/>)
            link_match = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', item, re.IGNORECASE)
            if not link_match:
                link_match = re.search(r'<link[^>]*>(.*?)</link>', item, re.DOTALL | re.IGNORECASE)
            article['link'] = unescape(link_match.group(1).strip()) if link_match else ''

            # Try to get full content from content:encoded, then content, then description
            content_match = re.search(r'<content:encoded[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</content:encoded>', item, re.DOTALL | re.IGNORECASE)
            if content_match:
                full_content = content_match.group(1).strip()
            else:
                content_match = re.search(r'<content[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</content[^>]*>', item, re.DOTALL | re.IGNORECASE)
                if content_match:
                    full_content = content_match.group(1).strip()
                else:
                    desc_match = re.search(r'<description[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL | re.IGNORECASE)
                    full_content = unescape(desc_match.group(1).strip()) if desc_match else ''

            article['fullContent'] = sanitize_html(full_content)
            article['description'] = re.sub(r'<[^>]+>', '', full_content)[:200]

            # Publication date (RSS: pubDate, Atom: published or updated)
            pub_date_match = re.search(r'<pubDate[^>]*>(.*?)</pubDate>', item, re.DOTALL | re.IGNORECASE)
            if not pub_date_match:
                pub_date_match = re.search(r'<published[^>]*>(.*?)</published>', item, re.DOTALL | re.IGNORECASE)
            if not pub_date_match:
                pub_date_match = re.search(r'<updated[^>]*>(.*?)</updated>', item, re.DOTALL | re.IGNORECASE)
            article['pubDate'] = parse_date(pub_date_match.group(1) if pub_date_match else None)

            # Image extraction: try media:content, media:thumbnail, enclosure, then inline img
            media_match = re.search(r'<media:content[^>]+url=["\']([^"\']+)["\']', item, re.IGNORECASE)
            if not media_match:
                media_match = re.search(r'<media:thumbnail[^>]+url=["\']([^"\']+)["\']', item, re.IGNORECASE)
            if not media_match:
                media_match = re.search(r'<enclosure[^>]+url=["\']([^"\']+)["\'][^>]+type=["\']image/', item, re.IGNORECASE)

            if media_match:
                image = media_match.group(1)
            else:
                image = extract_image_from_article(full_content)

            article['image'] = image if image and image.startswith('http') else None

            articles.append(article)
        except Exception:
            continue

    return articles


def categorize_article(title, description):
    """Categorize article based on content"""
    content = (title + ' ' + description).lower()
    
    categories = {
        'digital': ['digital', 'online', 'internet', 'web', 'seo', 'website', 'e-commerce', 'digital marketing'],
        'social': ['social media', 'social', 'instagram', 'facebook', 'twitter', 'linkedin', 'tiktok', 'social networks'],
        'branding': ['brand', 'branding', 'identity', 'logo', 'design', 'markenidentitÃ¤t'],
        'content': ['content', 'artikel', 'blog', 'writing', 'copywriting', 'storytelling'],
        'strategy': ['strategie', 'strategy', 'planning', 'marketing plan', 'goals', 'objectives']
    }
    
    for category, keywords in categories.items():
        if any(keyword in content for keyword in keywords):
            return category
    
    return 'digital'  # Default


def calculate_reading_time(text):
    """Calculate reading time in minutes"""
    words = len(text.split())
    minutes = max(1, round(words / 200))
    return minutes


def fetch_feeds():
    """Fetch and process all RSS feeds"""
    feeds = [
        {
            'url': 'https://blog.hubspot.com/marketing/rss.xml',
            'source': 'HubSpot Blog'
        },
        {
            'url': 'https://contentmarketinginstitute.com/feed/',
            'source': 'Content Marketing Institute'
        },
        {
            'url': 'https://www.socialmediatoday.com/feed/',
            'source': 'Social Media Today'
        },
        {
            'url': 'https://www.searchenginejournal.com/feed/',
            'source': 'Search Engine Journal'
        },
        {
            'url': 'https://www.marketingweek.com/feed/',
            'source': 'Marketing Week'
        },
        {
            'url': 'https://www.adweek.com/feed/',
            'source': 'Adweek'
        },
        {
            'url': 'https://feeds.feedburner.com/naborly',
            'source': 'Neil Patel'
        },
        {
            'url': 'https://moz.com/devblog/feed',
            'source': 'Moz'
        },
        {
            'url': 'https://www.socialmediaexaminer.com/feed/',
            'source': 'Social Media Examiner'
        },
        {
            'url': 'https://blog.hootsuite.com/feed/',
            'source': 'Hootsuite Blog'
        },
        {
            'url': 'https://sproutsocial.com/insights/feed/',
            'source': 'Sprout Social'
        },
        {
            'url': 'https://www.thinkwithgoogle.com/rss/',
            'source': 'Think with Google'
        }
    ]
    
    all_articles = []
    sources_seen = set()
    
    for feed_config in feeds:
        try:
            feed_xml = fetch_url(feed_config['url'], timeout=15)
            if not feed_xml:
                continue
            
            articles = extract_rss_content(feed_xml)
            
            for article in articles:
                article['source'] = feed_config['source']
                article['category'] = categorize_article(article['title'], article['description'])
                article['readingTime'] = calculate_reading_time(article.get('description', '') + ' ' + re.sub(r'<[^>]+>', '', article.get('fullContent', '')))

                # Try og:image fallback for articles without images
                if not article.get('image') and article.get('link'):
                    try:
                        page_html = fetch_url(article['link'], timeout=8)
                        if page_html:
                            og_img = extract_og_image(page_html)
                            if og_img and og_img.startswith('http'):
                                article['image'] = og_img
                    except Exception:
                        pass

                sources_seen.add(feed_config['source'])
                all_articles.append(article)
        
        except Exception:
            continue
    
    # Sort by date descending
    all_articles.sort(key=lambda x: x['pubDate'], reverse=True)
    
    # Keep only unique articles by title
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        if article['title'] not in seen_titles:
            unique_articles.append(article)
            seen_titles.add(article['title'])
    
    return unique_articles[:100], list(sources_seen)


def main():
    """Main entry point"""
    articles, sources = fetch_feeds()
    
    output_data = {
        'updated': datetime.now().isoformat() + 'Z',
        'total': len(articles),
        'sources': sorted(sources),
        'articles': articles
    }
    
    output_path = Path(__file__).parent.parent / 'data' / 'news.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f'Fetched {len(articles)} articles from {len(sources)} sources')
    print(f'Output saved to {output_path}')


if __name__ == '__main__':
    main()
