#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI Discovery Blog updater (stable).

- Fetches AI/tech news from Newsdata (last 48h)
- Quality filters (no 1-liners)
- Downloads/caches article image when possible
- Topic heroes / rotating heroes / final fallback
- Uses the article's real pubDate for filename and front-matter
- Skips duplicates by slug across the whole _posts folder
"""

from __future__ import annotations

import os
import re
import sys
import glob
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify

# ====== Config ======
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

# Image choices
GENERIC_FALLBACK = "/assets/ai-hero.svg"
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
USER_AGENT = "ai-discovery-bot/1.4 (+github actions)"

# ====== Helpers ======
def debug(msg: str) -> None:
    print(msg, flush=True)

def clean(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def ensure_dir(p: str) -> None:
    if not os.path.isdir(p):
        os.makedirs(p, exist_ok=True)

def yq(s: str) -> str:
    """YAML-safe quotes (escape double quotes)."""
    return clean(s).replace('"', r'\"')

def shorten(s: str, n: int = 300) -> str:
    s = clean(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

def parse_pubdate(s: Optional[str]) -> datetime:
    # Accept common formats; fall back to now (UTC)
    if not s:
        return datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def build_query() -> str:
    q = " OR ".join(KEYWORDS)
    return q if len(q) <= 95 else '"artificial intelligence" OR ai OR "machine learning"'

def newsdata_params(page: int | None = None) -> Dict[str, Any]:
    # last 48h window
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=48)).strftime("%Y-%m-%d")
    end   = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    p = {
        "apikey": API_KEY,
        "q": build_query(),
        "language": LANG,
        "category": CATEGORY,
        "from_date": start,
        "to_date": end,
    }
    if page:
        p["page"] = page
    return p

def call_api(page: int | None = None) -> Dict[str, Any]:
    r = requests.get(API_URL, params=newsdata_params(page), headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    return r.json()

def guess_ext(ct: str) -> str:
    ct = (ct or "").lower()
    if "svg" in ct: return ".svg"
    if "webp" in ct: return ".webp"
    if "png" in ct: return ".png"
    if "gif" in ct: return ".gif"
    return ".jpg"

def download_image(url: str, title: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25, stream=True)
        resp.raise_for_status()
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "image" not in ct:
            return None
        base = os.path.basename(urlparse(url).path) or slugify(title) or "img"
        root, ext = os.path.splitext(base)
        if ext.lower() not in IMG_EXT_WHITELIST:
            ext = guess_ext(ct)
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        filename = f"{slugify(root)}-{h}{ext}"
        ensure_dir(ASSET_CACHE_DIR)
        with open(os.path.join(ASSET_CACHE_DIR, filename), "wb") as f:
            for chunk in resp.iter_content(65536):
                if chunk:
                    f.write(chunk)
        return f"/{ASSET_CACHE_DIR}/{filename}"
    except Exception as e:
        debug(f"img download failed: {e}")
        return None

def detect_topic(t: str, d: str) -> Optional[str]:
    text = f"{t} {d}".lower()
    if any(k in text for k in ["policy", "regulation", "law", "ban"]): return "policy"
    if any(k in text for k in ["gpu", "chip", "nvidia", "amd", "hardware"]): return "chips"
    if any(k in text for k in ["stock", "market", "shares", "revenue", "valuation"]): return "markets"
    if any(k in text for k in ["research", "paper", "breakthrough", "study"]): return "research"
    if any(k in text for k in ["health", "medical", "doctor", "clinical"]): return "health"
    if any(k in text for k in ["education", "school", "classroom", "student"]): return "edu"
    return None

def rotating_hero(title: str) -> str:
    existing = [p for p in ROTATE_CANDIDATES if os.path.exists(p.lstrip("/"))]
    if not existing:
        return GENERIC_FALLBACK
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(existing)
    return existing[idx]

def pick_image(item: Dict[str, Any], title: str, desc: str) -> str:
    for k in ("image_url", "image"):
        url = clean(item.get(k))
        if url.startswith(("http://", "https://")):
            local = download_image(url, title)
            if local:
                return local
    topic = detect_topic(title, desc)
    if topic and os.path.exists(TOPIC_HEROES.get(topic, "").lstrip("/")):
        return TOPIC_HEROES[topic]
    return rotating_hero(title)

# ====== Fetch & build ======
def load_existing_slugs() -> set[str]:
    slugs = set()
    for path in glob.glob(os.path.join(POSTS_DIR, "*.md")):
        base = os.path.basename(path)
        # YYYY-mm-dd-<slug>.md
        parts = base.split("-", 3)
        if len(parts) >= 4:
            slug = parts[3][:-3]  # drop .md
            slugs.add(slug)
    return slugs

def make_slug(title: str) -> str:
    return slugify(title)[:80] or "post"

def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("API KEY not set (NEWSDATA_API_KEY or NEWS_API_KEY).")
    debug("📰 Fetching last 48h…")
    collected: List[Dict[str, Any]] = []
    seen = set()
    page = 1
    while len(collected) < limit and page <= 5:
        data = call_api(page)
        items = data.get("results") or []
        if not items:
            break
        for it in items:
            if len(collected) >= limit:
                break
            title = clean(it.get("title"))
            desc  = clean(it.get("description"))
            link  = clean(it.get("link") or it.get("url"))
            if not title or not link:
                continue
            if len(title) < 8 or len(desc) < 40:
                # too weak — avoid low value
                continue
            slug = make_slug(title)
            if slug in seen:
                continue
            pub = parse_pubdate(it.get("pubDate") or it.get("published_at"))
            img = pick_image(it, title, desc)
            collected.append({
                "title": title,
                "desc": desc,
                "link": link,
                "source": clean(it.get("source_id") or it.get("source") or "source"),
                "image": img,
                "pub": pub,
                "slug": slug,
            })
            seen.add(slug)
        page += 1
    return collected[:limit]

def fm_date(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).date().isoformat()

def build_md(a: Dict[str, Any]) -> str:
    fm = [
        "---",
        "layout: post",
        f'title: "{yq(a["title"])}"',
        f'date: {fm_date(a["pub"])}',
        f'excerpt: "{shorten(a["desc"], 300)}"',
        "categories: [ai, news]",
        f'image: "{a["image"] or GENERIC_FALLBACK}"',
        f'source: "{yq(a["source"])}"',
        f'source_url: "{yq(a["link"])}"',
        "---",
    ]
    body = a["desc"] or ""
    return "\n".join(fm) + "\n\n" + body + "\n"

def make_filename(a: Dict[str, Any]) -> str:
    date_part = fm_date(a["pub"])
    return os.path.join(POSTS_DIR, f"{date_part}-{a['slug']}.md")

def write_posts(arts: List[Dict[str, Any]]) -> int:
    ensure_dir(POSTS_DIR)
    existing_slugs = load_existing_slugs()
    written = 0
    for a in arts:
        if a["slug"] in existing_slugs:
            debug(f"↩︎ Skip duplicate slug: {a['slug']}")
            continue
        path = make_filename(a)
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_md(a))
        debug(f"✅ Wrote {os.path.basename(path)}")
        existing_slugs.add(a["slug"])
        written += 1
    return written

# ====== Main ======
def main():
    try:
        ensure_dir(ASSET_CACHE_DIR)
        # ensure cache tracked
        gk = os.path.join(ASSET_CACHE_DIR, ".gitkeep")
        if not os.path.exists(gk):
            with open(gk, "w", encoding="utf-8") as fp:
                fp.write("")
        arts = fetch_articles(MAX_POSTS)
        n = write_posts(arts)
        debug(f"Done. {n} new post(s).")
    except Exception as e:
        debug(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
