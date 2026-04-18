#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Blog Pipeline - Claude-powered post generator
- Fetches AI news from Newsdata.io
- Uses Claude API to write original, insightful posts
- Angle: plain English explanation + practical money/time opportunity
- Publishes to Jekyll _posts/
"""
from __future__ import annotations
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

EDITORIAL_PROMPT = """You write a blog called "AI, but make it useful" — a friendly, conversational blog for everyday curious people who want to understand AI without the hype.

For each post you receive a news article title and summary. Your job is to write an original blog post that:
1. Explains what this AI development actually is in plain, simple English (2-3 paragraphs max). Use analogies. Avoid jargon.
2. Answers "So what? How could I make money or save money from this?" with 2-3 concrete, specific, realistic ideas for regular people or small business owners.

Tone: Like a smart friend explaining it over coffee. Warm, direct, no fluff. Not a journalist, not a researcher.

IMPORTANT RULES:
- Never copy or closely paraphrase the original article. Write everything fresh in your own voice.
- No hype words like "revolutionary", "groundbreaking", "game-changing"
- Keep total length between 350-500 words
- End with one punchy sentence takeaway

Return ONLY the blog post body text. No title, no front matter, no markdown headers."""


def dbg(msg: str) -> None:
        print(msg, flush=True)


def clean(s: Optional[str]) -> str:
        if not s:
                    return ""
                return re.sub(r"\s+", " ", str(s)).strip()


def ensure_dir(p: str) -> None:
        os.makedirs(p, exist_ok=True)


def yml(s: str) -> str:
        return clean(s).replace('"', r'\"')


def shorten(s: str, n: int = 200) -> str:
        s = clean(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "..."


def guess_ext(ct: str) -> str:
        ct = (ct or "").lower()
    if "svg" in ct: return ".svg"
            if "webp" in ct: return ".webp"
                    if "png" in ct: return ".png"
                            if "gif" in ct: return ".gif"
                                    return ".jpg"


def download_image(url: str, title: str) -> Optional[str]:
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
        fname = f"{slugify(base) or 'img'}-{h}{ext}"
        ensure_dir(ASSET_CACHE_DIR)
        ap = os.path.join(ASSET_CACHE_DIR, fname)
        with open(ap, "wb") as f:
                        for chunk in r.iter_content(65536):
                                            if chunk:
                                                                    f.write(chunk)
                                                        return f"/{ASSET_CACHE_DIR}/{fname}"
except Exception:
        return None


def pick_image(item: Dict[str, Any], title: str) -> str:
        for k in ("image_url", "image"):
                    url = clean(item.get(k))
        if url and url.startswith(("http://", "https://")):
                        local = download_image(url, title)
                        if local:
                                            return local
                                return GENERIC_FALLBACK


def fetch_news(limit: int) -> List[Dict[str, Any]]:
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


def generate_post_with_claude(article: Dict[str, Any]) -> Optional[str]:
        if not ANTHROPIC_API_KEY:
                    raise SystemExit("ANTHROPIC_API_KEY not set")
    dbg(f"Generating post with Claude for: {article['title'][:60]}...")
    user_msg = f"Article title: {article['title']}\n\nArticle summary: {article['description']}"
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
    content = data.get("content", [])
    for block in content:
                if block.get("type") == "text":
                                return block["text"].strip()
                        return None


def build_post(article: Dict[str, Any], body: str) -> str:
        fm = [
                    "---",
                    "layout: post",
                    f'title: "{yml(article["title"])}"',
                    f'date: {datetime.now(timezone.utc).date().isoformat()}',
                    f'excerpt: "{shorten(article["description"], 200)}"',
                    "categories: [ai, practical]",
                    f'image: "{article.get("image") or GENERIC_FALLBACK}"',
                    f'source: "{yml(article.get("source", ""))}"',
                    f'source_url: "{yml(article.get("link", ""))}"',
                    "---",
        ]
    return "\n".join(fm) + "\n\n" + body + "\n"


def make_filename(title: str, pub: Optional[str]) -> str:
        date_part = (pub or datetime.now(timezone.utc).date().isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")


def write_post(article: Dict[str, Any], body: str) -> Optional[str]:
        ensure_dir(POSTS_DIR)
    path = make_filename(article["title"], article.get("pubDate"))
    if os.path.exists(path):
                dbg(f"Skip (exists): {os.path.basename(path)}")
        return None
    with open(path, "w", encoding="utf-8") as f:
                f.write(build_post(article, body))
    dbg(f"Written: {path}")
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
                                body = generate_post_with_claude(article)
                                if not body:
                                                    dbg(f"Claude returned empty for: {article['title'][:60]}")
                                                    continue
                                                result = write_post(article, body)
            if result:
                                created += 1
except Exception as e:
            dbg(f"Error processing article: {e}")
            continue

    dbg(f"Done. Created {created} post(s).")


if __name__ == "__main__":
        main()
