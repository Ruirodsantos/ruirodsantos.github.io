#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fetch AI news from Newsdata and write Jekyll posts to _posts/.
- Uses NEWSDATA_API_KEY from env
- Trims whitespace from the key
- Very conservative query to avoid 422s
"""

from __future__ import annotations
import os, re, sys, hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify

API_URL = "https://newsdata.io/api/1/news"

# Read and strip the key to avoid trailing spaces/newlines issues
_API_RAW = os.getenv("NEWSDATA_API_KEY", "")
API_KEY = (_API_RAW or "").strip()

LANG = "en"
CATEGORY = "technology"
MAX_POSTS = 10

POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/2.0 (+github actions)"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

def debug(msg: str) -> None:
    print(msg, flush=True)

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)

def yml(s: str) -> str:
    return clean_text(s).replace('"', r'\"')

def shorten(s: str, n: int = 280) -> str:
    s = clean_text(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

def call_api(page: int = 1) -> Dict[str, Any]:
    if not API_KEY:
        raise RuntimeError("NEWSDATA_API_KEY is empty.")
    params = {
        "apikey": API_KEY,
        # Keep it ultra-simple to avoid 422s. We’ll filter client-side.
        "q": "ai",
        "language": LANG,
        "page": page,
    }
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(API_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

def detect_topic(title: str, desc: str) -> str:
    t = f"{title} {desc}".lower()
    if any(k in t for k in ["policy", "regulation", "law", "ban"]): return "policy"
    if any(k in t for k in ["gpu", "chip", "nvidia", "amd", "hardware"]): return "chips"
    if any(k in t for k in ["stock", "market", "valuation", "shares"]): return "markets"
    if any(k in t for k in ["research", "paper", "study", "breakthrough"]): return "research"
    if any(k in t for k in ["health", "medical", "doctor", "clinical"]): return "health"
    if any(k in t for k in ["education", "school", "classroom", "student"]): return "edu"
    return "ai"

TOPIC_FALLBACK = {
    "policy":   "/assets/topic-policy.svg",
    "chips":    "/assets/topic-chips.svg",
    "markets":  "/assets/topic-markets.svg",
    "research": "/assets/topic-research.svg",
    "health":   "/assets/topic-health.svg",
    "edu":      "/assets/topic-edu.svg",
    "ai":       GENERIC_FALLBACK,
}

def pick_image_url(item: Dict[str, Any], title: str, desc: str) -> str:
    for k in ("image_url", "image"):
        u = clean_text(item.get(k))
        if u and u.startswith(("http://", "https://")):
            return u
    return TOPIC_FALLBACK.get(detect_topic(title, desc), GENERIC_FALLBACK)

def build_md(a: Dict[str, Any]) -> str:
    title = a["title"]
    excerpt = a.get("description") or ""
    fm = [
        "---",
        "layout: post",
        f'title: "{yml(title)}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{yml(shorten(excerpt, 300))}"',
        "categories: [ai, news]",
        f'image: "{a.get("image", GENERIC_FALLBACK)}"',
        f'source: "{yml(a.get("source_id", "source"))}"',
        f'source_url: "{yml(a.get("link", ""))}"',
        "---",
    ]
    body = excerpt or ""
    return "\n".join(fm) + "\n\n" + body + "\n"

def write_post(a: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    date_part = (a.get("pubDate") or datetime.now(timezone.utc).isoformat())[:10]
    slug = slugify(a["title"])[:80] or "post"
    path = os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")
    if os.path.exists(path):
        debug(f"skip (exists): {os.path.basename(path)}")
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_md(a))
    debug(f"wrote: {path}")
    return path

def main() -> None:
    if not API_KEY:
        print("❌ NEWSDATA_API_KEY not set.", flush=True)
        sys.exit(1)

    debug("🧠 Fetching articles (q=ai, language=en)…")
    collected: List[Dict[str, Any]] = []
    page = 1
    while len(collected) < MAX_POSTS and page <= 3:
        try:
            data = call_api(page)
        except requests.HTTPError as e:
            print(f"HTTP error: {e}", flush=True)
            print("Body:", getattr(e.response, "text", "")[:500], flush=True)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", flush=True)
            sys.exit(1)

        results = data.get("results") or []
        if not results:
            break

        for it in results:
            if len(collected) >= MAX_POSTS:
                break
            title = clean_text(it.get("title"))
            link  = clean_text(it.get("link"))
            desc  = clean_text(it.get("description"))
            if not title or not link:
                continue
            if "ai" not in f"{title} {desc}".lower():
                continue
            collected.append({
                "title": title,
                "description": desc,
                "link": link,
                "source_id": clean_text(it.get("source_id") or it.get("source") or "source"),
                "pubDate": clean_text(it.get("pubDate") or it.get("published_at") or ""),
                "image": pick_image_url(it, title, desc),
            })
        page += 1

    if not collected:
        debug("No items matched.")
        return

    created = 0
    for a in collected:
        if write_post(a):
            created += 1
    debug(f"Done. created={created}")

if __name__ == "__main__":
    main()
