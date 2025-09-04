#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-updater for AI Discovery Blog.
Com suporte para imagens dinâmicas:
- Usa a imagem original do artigo (faz download/cache em assets/cache).
- Caso falhe, tenta imagens por tópico (policy, chips, markets, research, health, edu).
- Caso falhe, roda por genéricos (ai-hero-1.svg, ai-hero-2.svg, etc).
- Último fallback: /assets/ai-hero.svg
"""

from __future__ import annotations

import os
import re
import sys
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, unquote
import requests
from slugify import slugify

# ---------------- Config ----------------
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY") or os.getenv("NEWS_API_KEY")

KEYWORDS = [
    "ai", "artificial intelligence", "machine learning",
    "openai", "anthropic", "meta ai", "google ai"
]
LANG = "en"
CATEGORY = "technology"
MAX_POSTS = 5

POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/1.2 (+github actions)"

TOPIC_HEROES = {
    "policy": "/assets/topic-policy.svg",
    "chips": "/assets/topic-chips.svg",
    "markets": "/assets/topic-markets.svg",
    "research": "/assets/topic-research.svg",
    "health": "/assets/topic-health.svg",
    "edu": "/assets/topic-edu.svg",
}

ROTATE_CANDIDATES = [
    "/assets/ai-hero-1.svg",
    "/assets/ai-hero-2.svg",
    "/assets/ai-hero-3.svg",
    "/assets/ai-hero-4.svg",
    "/assets/ai-hero-5.svg",
]

IMG_EXT_WHITELIST = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

# ---------------- Utils ----------------
def debug(msg: str) -> None:
    print(msg, flush=True)

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)

def shorten(s: str, max_len: int = 280) -> str:
    s = clean_text(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"

# ---------------- API ----------------
def build_query() -> str:
    q = " OR ".join(KEYWORDS)
    if len(q) > 95:
        q = '"artificial intelligence" OR ai OR "machine learning"'
    return q

def call_api(page: Optional[int] = None) -> Dict[str, Any]:
    params = {"apikey": API_KEY, "q": build_query(), "language": LANG, "category": CATEGORY}
    if page:
        params["page"] = page
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(API_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------------- Image helpers ----------------
def guess_ext_from_ct(ct: str) -> str:
    if "svg" in ct: return ".svg"
    if "webp" in ct: return ".webp"
    if "png" in ct: return ".png"
    if "gif" in ct: return ".gif"
    return ".jpg"

def download_and_cache_image(url: str, title: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, stream=True)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "")
        if "image" not in ct.lower():
            return None

        name = os.path.basename(urlparse(url).path) or slugify(title)
        base, ext = os.path.splitext(name)
        if ext.lower() not in IMG_EXT_WHITELIST:
            ext = guess_ext_from_ct(ct)

        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        filename = f"{slugify(base)}-{h}{ext}"
        ensure_dir(ASSET_CACHE_DIR)
        abs_path = os.path.join(ASSET_CACHE_DIR, filename)

        with open(abs_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                f.write(chunk)

        return f"/{ASSET_CACHE_DIR}/{filename}"
    except Exception:
        return None

def detect_topic(title: str, desc: str) -> Optional[str]:
    t = f"{title} {desc}".lower()
    if "policy" in t or "regulation" in t: return "policy"
    if "gpu" in t or "chip" in t: return "chips"
    if "stock" in t or "market" in t: return "markets"
    if "research" in t or "paper" in t: return "research"
    if "health" in t or "medical" in t: return "health"
    if "education" in t or "school" in t: return "edu"
    return None

def pick_rotating_hero(title: str) -> str:
    existing = [p for p in ROTATE_CANDIDATES if os.path.exists(p.lstrip("/"))]
    if not existing:
        return GENERIC_FALLBACK
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(existing)
    return existing[idx]

def pick_image(item: Dict[str, Any], title: str, desc: str) -> str:
    for k in ["image_url", "image"]:
        url = item.get(k)
        if url and url.startswith("http"):
            local = download_and_cache_image(url, title)
            if local:
                return local
    topic = detect_topic(title, desc)
    if topic and os.path.exists(TOPIC_HEROES.get(topic, "").lstrip("/")):
        return TOPIC_HEROES[topic]
    return pick_rotating_hero(title)

# ---------------- Posts ----------------
def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("API KEY not set")

    debug("Fetching AI articles...")
    collected: List[Dict[str, Any]] = []
    page = 1
    while len(collected) < limit and page <= 3:
        try:
            data = call_api(page)
        except Exception as e:
            debug(f"API error: {e}")
            break

        results = data.get("results") or []
        if not results:
            break

        for item in results:
            if len(collected) >= limit:
                break
            title = clean_text(item.get("title"))
            desc = clean_text(item.get("description"))
            link = clean_text(item.get("link"))
            if not title or not link:
                continue
            img = pick_image(item, title, desc)
            collected.append({
                "title": title,
                "description": desc,
                "link": link,
                "source_id": item.get("source_id", "source"),
                "image": img,
                "pubDate": item.get("pubDate") or datetime.now(timezone.utc).isoformat(),
            })
        page += 1
    return collected[:limit]

def build_markdown(article: Dict[str, Any]) -> str:
    safe_title = article["title"].replace('"', '\\"')
    safe_excerpt = (article.get("description") or "").replace('"', '\\"')
    fm = [
        "---",
        "layout: post",
        f'title: "{safe_title}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{shorten(safe_excerpt, 300)}"',
        "categories: [ai, news]",
        f'image: "{article.get("image") or GENERIC_FALLBACK}"',
        f'source: "{(article.get("source_id") or "source")}"',
        f'source_url: "{article.get("link")}"',
        "---",
    ]
    body = article.get("description") or ""
    return "\n".join(fm) + "\n\n" + body + "\n"

def make_filename(title: str, date_str: Optional[str] = None) -> str:
    date_part = (date_str or datetime.now(timezone.utc).date().isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")

def write_post(article: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    path = make_filename(article["title"], article.get("pubDate"))
    if os.path.exists(path):
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_markdown(article))
    return path

# ---------------- Main ----------------
def main():
    try:
        ensure_dir(ASSET_CACHE_DIR)
        articles = fetch_articles()
        for art in articles:
            write_post(art)
        debug("Done.")
    except Exception as e:
        debug(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
