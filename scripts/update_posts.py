#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-updater for AI Discovery Blog.

- Vai à Newsdata e busca artigos de IA
- Guarda imagem do próprio artigo (em assets/cache)
- Se falhar, usa heróis por tópico
- Se falhar, roda genéricos
- Último fallback: /assets/ai-hero.svg
- Escreve posts .md em _posts/
"""

from __future__ import annotations
import os
import re
import sys
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify

# ---------------- Config ----------------
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")

KEYWORDS = ["ai", "artificial intelligence", "machine learning",
            "openai", "anthropic", "meta ai", "google ai"]

LANG = "en"
MAX_POSTS = 10

POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/2.0 (+github actions)"

TOPIC_HEROES = {
    "policy":   "/assets/topic-policy.svg",
    "chips":    "/assets/topic-chips.svg",
    "markets":  "/assets/topic-markets.svg",
    "research": "/assets/topic-research.svg",
    "health":   "/assets/topic-health.svg",
    "edu":      "/assets/topic-edu.svg",
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
    return re.sub(r"\s+", " ", str(s)).strip()


def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def yml_escape(s: str) -> str:
    return clean_text(s).replace('"', r'\"')


def shorten(s: str, max_len: int = 280) -> str:
    s = clean_text(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


# ---------------- API ----------------
def call_api(page: Optional[int] = None) -> Dict[str, Any]:
    if not API_KEY:
        raise ValueError("❌ NEWS_API_KEY not set (GitHub Secrets).")

    params = {
        "apikey": API_KEY,
        "q": "ai OR \"artificial intelligence\" OR \"machine learning\"",
        "language": LANG,
        "page": page or 1
    }
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(API_URL, params=params, headers=headers, timeout=20)
    debug(f"🌐 GET {r.url}")
    r.raise_for_status()
    return r.json()


# ---------------- Image helpers ----------------
def guess_ext_from_ct(ct: str) -> str:
    ct = (ct or "").lower()
    if "svg" in ct: return ".svg"
    if "webp" in ct: return ".webp"
    if "png" in ct: return ".png"
    if "gif" in ct: return ".gif"
    return ".jpg"


def download_and_cache_image(url: str, title: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, stream=True)
        resp.raise_for_status()
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "image" not in ct:
            return None

        path_name = os.path.basename(urlparse(url).path) or slugify(title)
        base, ext = os.path.splitext(path_name)
        if ext.lower() not in IMG_EXT_WHITELIST:
            ext = guess_ext_from_ct(ct)

        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        filename = f"{slugify(base) or 'img'}-{h}{ext}"

        ensure_dir(ASSET_CACHE_DIR)
        abs_path = os.path.join(ASSET_CACHE_DIR, filename)

        with open(abs_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                if chunk:
                    f.write(chunk)

        return f"/{ASSET_CACHE_DIR}/{filename}"
    except Exception as e:
        debug(f"⚠️ img download fail: {e}")
        return None


def detect_topic(title: str, desc: str) -> Optional[str]:
    t = f"{title} {desc}".lower()
    if any(k in t for k in ["policy", "regulation", "law", "ban"]): return "policy"
    if any(k in t for k in ["gpu", "chip", "nvidia", "amd", "hardware"]): return "chips"
    if any(k in t for k in ["stock", "market", "shares", "revenue", "valuation"]): return "markets"
    if any(k in t for k in ["research", "paper", "breakthrough", "study"]): return "research"
    if any(k in t for k in ["health", "medical", "doctor", "clinical"]): return "health"
    if any(k in t for k in ["education", "school", "classroom", "student"]): return "edu"
    return None


def pick_rotating_hero(title: str) -> str:
    existing = [p for p in ROTATE_CANDIDATES if os.path.exists(p.lstrip("/"))]
    if not existing:
        return GENERIC_FALLBACK
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(existing)
    return existing[idx]


def pick_image(item: Dict[str, Any], title: str, desc: str) -> str:
    for k in ("image_url", "image"):
        url = clean_text(item.get(k))
        if url and url.startswith(("http://", "https://")):
            local = download_and_cache_image(url, title)
            if local:
                return local

    topic = detect_topic(title, desc)
    if topic:
        candidate = TOPIC_HEROES.get(topic)
        if candidate and os.path.exists(candidate.lstrip("/")):
            return candidate

    return pick_rotating_hero(title)


# ---------------- Posts ----------------
def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    debug("📰 Fetching articles...")
    collected: List[Dict[str, Any]] = []
    page = 1

    while len(collected) < limit and page <= 3:
        try:
            data = call_api(page)
        except Exception as e:
            debug(f"❌ API error (page {page}): {e}")
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
            source_id = clean_text(item.get("source_id") or item.get("source") or "source")
            pubdate = clean_text(item.get("pubDate") or item.get("published_at") or "")

            if not title or not link:
                continue

            image_path = pick_image(item, title, desc)

            collected.append({
                "title": title,
                "description": desc,
                "link": link,
                "source_id": source_id,
                "image": image_path,
                "pubDate": pubdate or datetime.now(timezone.utc).isoformat(),
            })

        page += 1

    return collected[:limit]


def build_markdown(article: Dict[str, Any]) -> str:
    safe_title = yml_escape(article["title"])
    safe_excerpt = yml_escape(article.get("description") or "")
    image = article.get("image") or GENERIC_FALLBACK
    source = yml_escape(article.get("source_id") or "source")
    source_url = yml_escape(article.get("link") or "")

    fm = [
        "---",
        "layout: post",
        f'title: "{safe_title}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{shorten(safe_excerpt, 300)}"',
        "categories: [ai, news]",
        f'image: "{image}"',
        f'source: "{source}"',
        f'source_url: "{source_url}"',
        "---",
    ]
    body = article.get("description") or ""
    return "\n".join(fm) + "\n\n" + body + "\n"


def make_filename(title: str, link: Optional[str] = None, date_str: Optional[str] = None) -> str:
    date_part = (date_str or datetime.now(timezone.utc).date().isoformat())[:10]
    base = slugify(title)[:60] or "post"
    suffix = hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:6]
    return os.path.join(POSTS_DIR, f"{date_part}-{base}-{suffix}.md")


def write_post(article: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    path = make_filename(article["title"], link=article.get("link"), date_str=article.get("pubDate"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_markdown(article))
    debug(f"✅ Wrote: {path}")
    return path


# ---------------- Main ----------------
def main():
    try:
        ensure_dir(ASSET_CACHE_DIR)
        ensure_dir(POSTS_DIR)

        articles = fetch_articles()
        created = 0
        for art in articles:
            if write_post(art):
                created += 1

        debug(f"🎉 Done. {created} new post(s).")
    except Exception as e:
        debug(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
