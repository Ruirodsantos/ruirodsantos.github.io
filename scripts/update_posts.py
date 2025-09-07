#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI Discovery Blog updater (Newsdata.io)
- Safe query (<=100 chars), handles 422s & pagination
- Pulls article image; if missing, uses topic hero or rotating generic
- Caches downloaded images in assets/cache
- Writes Jekyll posts with clean, escaped front-matter

Requires:
  pip install requests python-slugify

Env:
  NEWSDATA_API_KEY (preferred)
"""

from __future__ import annotations

import os
import re
import sys
import json
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify

# ---------------- Config ----------------
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY")

# Keep short to respect Newsdata 100-char query limit
KEYWORDS = [
    "ai", "artificial intelligence", "machine learning",
    "openai", "anthropic", "google ai", "meta ai",
]
LANG = "en"
CATEGORY = "technology"
MAX_POSTS = 5
PAGES_MAX = 3               # up to 3 pages to avoid abuse / 422 loops
WINDOW_HOURS = 48           # fetch last 48h to reduce repeats

POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
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
def log(msg: str) -> None:
    print(msg, flush=True)

def clean(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)

def shorten(s: str, n: int) -> str:
    s = clean(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

def yml_escape(s: str) -> str:
    return clean(s).replace('"', r'\"')

# ---------------- Query building ----------------
def build_query() -> str:
    # Use quotes only where necessary; keep it short
    parts = []
    length = 0
    for kw in KEYWORDS:
        token = f"\"{kw}\"" if " " in kw else kw
        # +4 for " OR "
        add = len(token) if not parts else len(token) + 4
        if length + add > 95:  # leave margin under 100
            break
        parts.append(token)
        length += add
    if not parts:
        parts = ["ai"]
    return " OR ".join(parts)

# ---------------- API ----------------
def call_api(page: Optional[int], from_date: str, to_date: str) -> Dict[str, Any]:
    params = {
        "apikey": API_KEY,
        "q": build_query(),
        "language": LANG,
        "category": CATEGORY,
        "from_date": from_date,
        "to_date": to_date,
    }
    if page:
        params["page"] = page
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(API_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------------- Images ----------------
def guess_ext_from_ct(ct: str) -> str:
    ct = (ct or "").lower()
    if "svg" in ct: return ".svg"
    if "webp" in ct: return ".webp"
    if "png" in ct: return ".png"
    if "gif" in ct: return ".gif"
    return ".jpg"

def download_cache_image(url: str, title: str) -> Optional[str]:
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
        dest = os.path.join(ASSET_CACHE_DIR, filename)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(65536):
                if chunk:
                    f.write(chunk)
        return f"/{ASSET_CACHE_DIR}/{filename}"
    except Exception as e:
        log(f"img skip: {e}")
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

def rotating_hero(title: str) -> str:
    candidates = [p for p in ROTATE_CANDIDATES if os.path.exists(p.lstrip("/"))]
    if not candidates:
        return GENERIC_FALLBACK
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(candidates)
    return candidates[idx]

def choose_image(item: Dict[str, Any], title: str, desc: str) -> str:
    for k in ("image_url", "image"):
        url = clean(item.get(k))
        if url.startswith(("http://", "https://")):
            local = download_cache_image(url, title)
            if local:
                return local
    topic = detect_topic(title, desc)
    if topic:
        hero = TOPIC_HEROES.get(topic)
        if hero and os.path.exists(hero.lstrip("/")):
            return hero
    return rotating_hero(title)

# ---------------- Fetch & Write ----------------
def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("NEWSDATA_API_KEY not set")

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=WINDOW_HOURS)).strftime("%Y-%m-%d")
    to_date   = now.strftime("%Y-%m-%d")

    log(f"📰 Fetching last {WINDOW_HOURS}h…")
    collected: List[Dict[str, Any]] = []
    page = 1

    while len(collected) < limit and page <= PAGES_MAX:
        try:
            data = call_api(page, from_date, to_date)
        except requests.HTTPError as e:
            # Print URL summary for 422 troubleshooting
            log(f"Error: {e}")
            break
        except Exception as e:
            log(f"Error: {e}")
            break

        results = data.get("results") or []
        if not results:
            break

        for item in results:
            if len(collected) >= limit:
                break
            title = clean(item.get("title"))
            desc = clean(item.get("description"))
            link = clean(item.get("link") or item.get("url"))
            source = clean(item.get("source_id") or item.get("source") or "source")
            pdt = clean(item.get("pubDate") or item.get("published_at") or "")

            if not title or not link:
                continue

            img = choose_image(item, title, desc)
            collected.append({
                "title": title,
                "description": desc,
                "link": link,
                "source": source,
                "image": img,
                "pubDate": pdt or now.isoformat(),
            })
        page += 1

    return collected[:limit]

def build_markdown(a: Dict[str, Any]) -> str:
    fm = [
        "---",
        "layout: post",
        f'title: "{yml_escape(a["title"])}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{yml_escape(shorten(a.get("description",""), 300))}"',
        "categories: [ai, news]",
        f'image: "{a.get("image") or GENERIC_FALLBACK}"',
        f'source: "{yml_escape(a.get("source") or "source")}"',
        f'source_url: "{yml_escape(a.get("link") or "")}"',
        "---",
    ]
    body = a.get("description") or ""
    return "\n".join(fm) + "\n\n" + body + "\n"

def make_filename(title: str, date_str: Optional[str]) -> str:
    date_part = (date_str or datetime.now(timezone.utc).date().isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")

def write_post(a: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    path = make_filename(a["title"], a.get("pubDate"))
    if os.path.exists(path):
        log(f"↩︎ Skip (exists): {os.path.basename(path)}")
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_markdown(a))
    log(f"✅ Wrote: {path}")
    return path

# ---------------- Main ----------------
def main() -> None:
    try:
        ensure_dir(ASSET_CACHE_DIR)
        # keep the dir in git
        gk = os.path.join(ASSET_CACHE_DIR, ".gitkeep")
        if not os.path.exists(gk):
            with open(gk, "w", encoding="utf-8") as fh:
                fh.write("")

        arts = fetch_articles()
        created = 0
        for a in arts:
            if write_post(a):
                created += 1
        log(f"🎉 Done. {created} new post(s).")
    except Exception as e:
        log(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
