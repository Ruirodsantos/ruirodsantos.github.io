#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, hashlib, json
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import requests
from slugify import slugify

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

MAX_POSTS = 3
POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
USER_AGENT = "ai-blog-bot/4.0"

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://feeds.feedburner.com/venturebeat/SZYF",
    "https://www.technologyreview.com/feed/",
    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
]

EDITORIAL_PROMPT = (
    "You write a blog called AI but make it useful. "
    "A friendly conversational blog for everyday curious people who want to understand AI without the hype. "
    "For each post you receive a news article title and summary. "
    "Write an original blog post that explains what this AI development is in plain simple English using 2-3 paragraphs with analogies and no jargon, "
    "then answers how the reader could make money or save money from this with 2-3 concrete realistic ideas for regular people or small business owners. "
    "Tone: Like a smart friend explaining it over coffee. Warm, direct, no fluff. "
    "Never copy or closely paraphrase the original article. "
    "No hype words like revolutionary or groundbreaking. "
    "Keep total length between 350-500 words. "
    "End with one punchy sentence takeaway. "
    "Return ONLY the blog post body text. No title, no front matter, no markdown headers."
)


def dbg(msg):
    print(msg, flush=True)


def clean(s):
    if not s:
        return ""
    return re.sub(r"\\s+", " ", str(s)).strip()


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)


def yml_safe(s):
    s = clean(s)
    s = s.replace('"', "'")
    s = s.replace("\\", "")
    return s


def shorten(s, n=200):
    s = clean(s)
    return s if len(s) <= n else s[:n - 1].rstrip() + "..."


def fetch_pexels_image(query):
    if not PEXELS_API_KEY:
        return None
    try:
        keywords = " ".join(query.split()[:4])
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": keywords, "per_page": 5, "orientation": "landscape"},
            timeout=15
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if photos:
            url = photos[0]["src"]["large2x"]
            dbg("Image found: " + url[:60])
            return url
    except Exception as e:
        dbg("Pexels error: " + str(e))
    return None


def fetch_rss(url):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item"):
            title = clean(item.findtext("title") or "")
            link = clean(item.findtext("link") or "")
            desc = clean(item.findtext("description") or "")
            desc = re.sub(r"<[^>]+>", "", desc)
            pub = clean(item.findtext("pubDate") or "")
            if title and link and len(desc) > 30:
                items.append({"title": title, "link": link, "description": desc, "pubDate": pub})
        return items
    except Exception as e:
        dbg("RSS error " + url + ": " + str(e))
        return []


def fetch_news(limit):
    dbg("Fetching from RSS feeds...")
    all_items = []
    for feed_url in RSS_FEEDS:
        items = fetch_rss(feed_url)
        dbg("Got " + str(len(items)) + " items from " + feed_url)
        all_items.extend(items)
        if len(all_items) >= limit * 5:
            break
    return all_items


def generate_post(article):
    if not ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY not set")
    dbg("Generating post for: " + article["title"][:60])
    user_msg = "Article title: " + article["title"] + "\\n\\nArticle summary: " + article["description"][:500]
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1000,
        "system": EDITORIAL_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    r = requests.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    for block in data.get("content", []):
        if block.get("type") == "text":
            return block["text"].strip()
    return None


def build_post(article, body, image_url):
    today = datetime.now(timezone.utc).date().isoformat()
    lines = [
        "---",
        "layout: post",
        'title: "' + yml_safe(article["title"]) + '"',
        "date: " + today,
        'excerpt: "' + yml_safe(shorten(article["description"], 160)) + '"',
        "categories: [ai, practical]",
        'image: "' + image_url + '"',
        'source_url: "' + yml_safe(article.get("link", "")) + '"',
        "---",
    ]
    return "\\n".join(lines) + "\\n\\n" + body + "\\n"


def make_filename(title):
    date_part = datetime.now(timezone.utc).date().isoformat()
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, date_part + "-" + slug + ".md")


def write_post(article, body, image_url):
    ensure_dir(POSTS_DIR)
    path = make_filename(article["title"])
    if os.path.exists(path):
        dbg("Skip (exists): " + os.path.basename(path))
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_post(article, body, image_url))
    dbg("Written: " + path)
    return path


def main():
    ensure_dir(ASSET_CACHE_DIR)
    gk = os.path.join(ASSET_CACHE_DIR, ".gitkeep")
    if not os.path.exists(gk):
        open(gk, "w").close()

    articles = fetch_news(MAX_POSTS)
    dbg("Total candidates: " + str(len(articles)))

    if not articles:
        dbg("No articles fetched.")
        return

    created = 0
    for article in articles:
        if created >= MAX_POSTS:
            break
        try:
            image_url = fetch_pexels_image(article["title"])
            if not image_url:
                dbg("No image found for: " + article["title"][:60] + " — skipping")
                continue

            body = generate_post(article)
            if not body:
                dbg("Empty response for: " + article["title"][:60])
                continue

            result = write_post(article, body, image_url)
            if result:
                created += 1
        except Exception as e:
            dbg("Error: " + str(e))
            continue

    dbg("Done. Created " + str(created) + " post(s).")


if __name__ == "__main__":
    main()
