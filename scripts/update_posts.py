#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, sys, hashlib, json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify

NEWS_API_URL = "https://newsdata.io/api/1/news"
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

LANG = "en"
MAX_POSTS = 3
POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/v2/1.0"
IMG_EXT_OK = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

EDITORIAL_PROMPT = (
    "You write a blog called AI but make it useful. "
    "A friendly conversational blog for everyday curious people who want to understand AI without the hype. "
    "For each post you receive a news article title and summary. "
    "Write an original blog post that: "
    "1. Explains what this AI development actually is in plain simple English using 2-3 paragraphs. Use analogies. Avoid jargon. "
    "2. Answers So what? How could I make money or save money from this? with 2-3 concrete specific realistic ideas for regular people or small business owners. "
    "Tone: Like a smart friend explaining it over coffee. Warm, direct, no fluff. "
    "RULES: Never copy or closely paraphrase the original article. "
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
    return re.sub(r"\s+", " ", str(s)).strip()


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)


def yml(s):
    return clean(s).replace('"', '\\"')


def shorten(s, n=200):
    s = clean(s)
    return s if len(s) <= n else s[:n - 1].rstrip() + "..."


def guess_ext(ct):
    ct = (ct or "").lower()
    if "svg" in ct:
        return ".svg"
    if "webp" in ct:
        return ".webp"
    if "png" in ct:
        return ".png"
    if "gif" in ct:
        return ".gif"
    return ".jpg"


def download_image(url, title):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, stream=True)
        r.raise_for_status()
        ct = (r.headers.get("Content-Type") or "").lower()
        if "image" not in ct:
            return None
        name = os.path.basename(urlparse(url).path) or slugify(title)
        base, ext = os.path.splitext(name)
        if ext.lower() not in IMG_EXT_OK:
            ext = guess_ext(ct)
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        fname = slugify(base or "img") + "-" + h + ext
        ensure_dir(ASSET_CACHE_DIR)
        ap = os.path.join(ASSET_CACHE_DIR, fname)
        with open(ap, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)
        return "/" + ASSET_CACHE_DIR + "/" + fname
    except Exception:
        return None


def pick_image(item, title):
    for k in ("image_url", "image"):
        url = clean(item.get(k))
        if url and url.startswith(("http://", "https://")):
            local = download_image(url, title)
            if local:
                return local
    return GENERIC_FALLBACK


def fetch_news(limit):
    if not NEWS_API_KEY:
        raise SystemExit("NEWS_API_KEY not set")
    dbg("Fetching news articles...")
    out = []
    page = 1
    while len(out) < limit and page <= 2:
        params = {"apikey": NEWS_API_KEY, "q": "artificial intelligence", "language": LANG, "page": page}
        r = requests.get(NEWS_API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=25)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            break
        for it in results:
            if len(out) >= limit:
                break
            title = clean(it.get("title"))
            link = clean(it.get("link") or it.get("url"))
            if not title or not link:
                continue
            desc = clean(it.get("description") or it.get("content") or "")
            if not desc or len(desc) < 50:
                continue
            out.append({
                "title": title,
                "description": desc,
                "link": link,
                "source": clean(it.get("source_id") or "source"),
                "pubDate": clean(it.get("pubDate") or ""),
                "image": pick_image(it, title),
            })
        page += 1
    return out[:limit]


def generate_post(article):
    if not ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY not set")
    dbg("Generating post for: " + article["title"][:60])
    user_msg = "Article title: " + article["title"] + "\n\nArticle summary: " + article["description"]
    payload = {
        "model": "claude-sonnet-4-20250514",
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


def build_post(article, body):
    today = datetime.now(timezone.utc).date().isoformat()
    lines = [
        "---",
        "layout: post",
        'title: "' + yml(article["title"]) + '"',
        "date: " + today,
        'excerpt: "' + shorten(article["description"], 200) + '"',
        "categories: [ai, practical]",
        'image: "' + (article.get("image") or GENERIC_FALLBACK) + '"',
        'source: "' + yml(article.get("source", "")) + '"',
        'source_url: "' + yml(article.get("link", "")) + '"',
        "---",
    ]
    return "\n".join(lines) + "\n\n" + body + "\n"


def make_filename(title, pub):
    date_part = (pub or datetime.now(timezone.utc).date().isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, date_part + "-" + slug + ".md")


def write_post(article, body):
    ensure_dir(POSTS_DIR)
    path = make_filename(article["title"], article.get("pubDate"))
    if os.path.exists(path):
        dbg("Skip (exists): " + os.path.basename(path))
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_post(article, body))
    dbg("Written: " + path)
    return path


def main():
    ensure_dir(ASSET_CACHE_DIR)
    gk = os.path.join(ASSET_CACHE_DIR, ".gitkeep")
    if not os.path.exists(gk):
        open(gk, "w").close()
    articles = fetch_news(MAX_POSTS)
    if not articles:
        dbg("No articles fetched.")
        return
    created = 0
    for article in articles:
        try:
            body = generate_post(article)
            if not body:
                dbg("Empty response for: " + article["title"][:60])
                continue
            result = write_post(article, body)
            if result:
                created += 1
        except Exception as e:
            dbg("Error: " + str(e))
            continue
    dbg("Done. Created " + str(created) + " post(s).")


if __name__ == "__main__":
    main()
