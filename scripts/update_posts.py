#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-updater for AI Discovery Blog.

- Fetches AI news from Newsdata
- Caches article images locally when possible
- Falls back to topic heroes / rotating heroes / generic hero
- Filters to last 24 hours only
- De-duplicates by URL (and fuzzy title) using data/seen.json (7-day window)
- Writes Jekyll posts into _posts/

Requires:
  pip install requests python-slugify

Env:
  NEWSDATA_API_KEY  (or NEWS_API_KEY)
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import math
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
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
SEEN_DB_PATH = "data/seen.json"       # URL hashes we already posted
SEEN_DAYS_KEEP = 7                    # keep seen entries for N days
RECENT_WINDOW_HOURS = 24              # only accept items newer than this window

GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/1.4 (+github actions)"

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


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------- Seen DB ----------------
def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def load_seen() -> Dict[str, float]:
    """Return {hash: epoch_seconds}."""
    try:
        with open(SEEN_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: float(v) for k, v in data.items()}
    except Exception:
        return {}


def save_seen(d: Dict[str, float]) -> None:
    ensure_dir(os.path.dirname(SEEN_DB_PATH))
    with open(SEEN_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def prune_seen(d: Dict[str, float], keep_days: int = SEEN_DAYS_KEEP) -> Dict[str, float]:
    cutoff = time.time() - keep_days * 86400
    return {k: v for k, v in d.items() if v >= cutoff}


def mark_seen(d: Dict[str, float], url: str, title: str) -> None:
    d[_hash(url)] = time.time()
    # also mark by title (less strict) to avoid same story w/ different URLs
    d[_hash(title.lower())] = time.time()


def already_seen(d: Dict[str, float], url: str, title: str) -> bool:
    h1 = _hash(url)
    h2 = _hash(title.lower())
    return (h1 in d) or (h2 in d)


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
    except Exception:
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


# ---------------- Date helpers ----------------
def parse_pubdate(item: Dict[str, Any]) -> Optional[datetime]:
    raw = clean_text(item.get("pubDate") or item.get("published_at") or "")
    if not raw:
        return None
    # try ISO first
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw)
    except Exception:
        pass
    # try lax parse (YYYY-MM-DD …)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        try:
            return datetime.fromisoformat(m.group(1) + "T00:00:00+00:00")
        except Exception:
            return None
    return None


def is_recent(dt: Optional[datetime], hours: int = RECENT_WINDOW_HOURS) -> bool:
    if not dt:
        return False
    return (now_utc() - dt) <= timedelta(hours=hours)


# ---------------- Posts ----------------
def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("API KEY not set (NEWSDATA_API_KEY or NEWS_API_KEY).")

    debug("📰 Fetching AI articles (unique & last 24h)…")
    collected: List[Dict[str, Any]] = []
    page = 1

    seen = prune_seen(load_seen(), SEEN_DAYS_KEEP)

    while len(collected) < limit and page <= 4:
        try:
            data = call_api(page)
        except Exception as e:
            debug(f"API error (page {page}): {e}")
            break

        results = data.get("results") or []
        if not results:
            break

        for item in results:
            if len(collected) >= limit:
                break

            title = clean_text(item.get("title"))
            desc = clean_text(item.get("description"))
            link = clean_text(item.get("link") or item.get("url"))
            if not title or not link:
                continue

            # 24h filter
            dt = parse_pubdate(item) or now_utc()
            if not is_recent(dt):
                continue

            # duplicate filter (URL or "near" title)
            if already_seen(seen, link, title):
                continue

            image_path = pick_image(item, title, desc)
            source_id = clean_text(item.get("source_id") or item.get("source") or "source")

            collected.append({
                "title": title,
                "description": desc,
                "link": link,
                "source_id": source_id,
                "image": image_path,
                "pubDate": dt.isoformat(),
            })

            # mark as seen immediately (prevents double from later pages)
            mark_seen(seen, link, title)

        page += 1

    save_seen(seen)
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
        f'date: {now_utc().date().isoformat()}',
        f'excerpt: "{shorten(safe_excerpt, 300)}"',
        "categories: [ai, news]",
        f'image: "{image}"',
        f'source: "{source}"',
        f'source_url: "{source_url}"',
        "---",
    ]

    # simple body (you can keep your richer 'enrich_text' if you want)
    body = article.get("description") or ""
    return "\n".join(fm) + "\n\n" + body + "\n"


def make_filename(title: str, date_str: Optional[str] = None) -> str:
    date_part = (date_str or now_utc().date().isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")


def write_post(article: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    path = make_filename(article["title"], article.get("pubDate"))
    if os.path.exists(path):
        debug(f"↩︎ Skip (exists): {os.path.basename(path)}")
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_markdown(article))
    debug(f"✅ Wrote: {path}")
    return path


# ---------------- Main ----------------
def main():
    try:
        ensure_dir(ASSET_CACHE_DIR)
        # ensure .gitkeep so cache is committed if needed
        ensure_dir(os.path.dirname(SEEN_DB_PATH))
        gk = os.path.join(ASSET_CACHE_DIR, ".gitkeep")
        if not os.path.exists(gk):
            with open(gk, "w", encoding="utf-8") as fh:
                fh.write("")

        articles = fetch_articles()
        created = 0
        for art in articles:
            if write_post(art):
                created += 1
        debug(f"Done. {created} new post(s).")
    except Exception as e:
        debug(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
