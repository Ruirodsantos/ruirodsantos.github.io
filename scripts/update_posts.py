#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate daily blog posts from Newsdata.io with quality filtering.

- Pulls 1–2 pages (without sending page=1 on the first request).
- Retries once without 'category' if Newsdata returns 422 (pagination quirk).
- Creates up to MAX_POSTS posts in _posts/.
- Skips low-quality or off-topic items.
"""

from __future__ import annotations

import os
import re
import json
import time
import html
import shutil
import string
import datetime as dt
from pathlib import Path
from typing import Dict, List, Optional

import requests
from slugify import slugify

# ========= Configuration =========

API_URL = "https://newsdata.io/api/1/news"

# Read API key from either env var name
API_KEY = os.getenv("NEWS_API_KEY") or os.getenv("NEWSDATA_API_KEY")
if not API_KEY:
    raise ValueError("❌ API_KEY not found. Set NEWS_API_KEY (or NEWSDATA_API_KEY) in repo secrets/variables.")

# Query and filtering
KEYWORDS = [
    "artificial intelligence",
    "AI",
    "machine learning",
    "generative AI",
    "openai",
    "anthropic",
    "google ai",
    "meta ai",
    "llm",
]

QUERY = " OR ".join(KEYWORDS)
LANGUAGE = "en"
CATEGORY = "technology"  # we will drop it on retry if 422 happens

# Post generation
MAX_POSTS = 5
POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(exist_ok=True)

MIN_DESC_CHARS = 140           # skip entries with too little text
MIN_UNIQUE_WORDS = 20          # rough quality gate
RECENT_WINDOW_HOURS = 48       # only keep last 48h

# Basic stop-terms to avoid sport/broadcast/program listings, paywalls, etc.
LOW_QUALITY_MARKERS = [
    "ONLY AVAILABLE IN PAID PLANS",
    "subscription required",
    "paywall",
    "watch live",
    "broadcasts",
    "fixture",
    "br 25", "premier league", "bundesliga",
    "rangers x celtic",
]

# ========= Utilities =========

def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def parse_pubdate(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    # Newsdata pubDate examples: "2025-09-02 19:21:00"
    # Assume it is UTC-like without timezone; parse naïvely then set UTC
    try:
        dt_naive = dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return dt_naive.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None

def strip_html(x: str) -> str:
    # remove basic HTML tags
    x = re.sub(r"<br\s*/?>", " ", x, flags=re.I)
    x = re.sub(r"<.*?>", "", x, flags=re.S)
    x = html.unescape(x)
    return x.strip()

def safe_excerpt(text: str, limit_words: int = 50) -> str:
    words = text.split()
    if len(words) <= limit_words:
        return text
    return " ".join(words[:limit_words]).rstrip(",.;:") + "…"

def text_quality_ok(title: str, desc: str) -> bool:
    t = f"{title}\n{desc}".lower()
    if any(m.lower() in t for m in LOW_QUALITY_MARKERS):
        return False
    if len(desc) < MIN_DESC_CHARS:
        return False
    uniq = set(w.strip(string.punctuation).lower() for w in desc.split())
    uniq = {w for w in uniq if w}
    if len(uniq) < MIN_UNIQUE_WORDS:
        return False
    return True

def load_existing_titles_and_links() -> tuple[set[str], set[str]]:
    titles: set[str] = set()
    links: set[str] = set()
    for p in POSTS_DIR.glob("*.md"):
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        # very light-weight YAML scan for title/link
        m_title = re.search(r'^title:\s*"(.*)"\s*$', txt, flags=re.M)
        m_source = re.search(r"^source:\s*(.+?)\s*$", txt, flags=re.M)
        if m_title:
            titles.add(m_title.group(1).strip())
        if m_source:
            links.add(m_source.group(1).strip())
    return titles, links

# ========= API calling (robust) =========

BASE_PARAMS = {
    "q": QUERY,
    "language": LANGUAGE,
    "category": CATEGORY,   # will be removed on retry if 422
    # DO NOT include 'page' here; we only add it for page>1
}

def call_api(params: Dict) -> Dict:
    """
    Call Newsdata.io and return JSON.
    - Don't send page=1 (omit page for first call).
    - If 422, retry once with category removed and page removed.
    """
    def _do_call(q: Dict) -> requests.Response:
        q = dict(q)
        q["apikey"] = API_KEY
        if q.get("page") == 1:
            q.pop("page", None)
        return requests.get(API_URL, params=q, timeout=30)

    resp = _do_call(params)
    if resp.status_code == 422:
        # Retry once with no 'category' and no 'page'
        p2 = dict(params)
        p2.pop("category", None)
        p2.pop("page", None)
        resp = _do_call(p2)

    # If still not ok, raise
    if not resp.ok:
        # Log some help text if provider returns JSON error
        try:
            data = resp.json()
            print(f"⚠️ API error ({resp.status_code}): {json.dumps(data)}")
        except Exception:
            print(f"⚠️ API error ({resp.status_code}): {resp.text[:500]}")
        resp.raise_for_status()

    return resp.json()

def fetch_latest(limit: int = MAX_POSTS) -> List[Dict]:
    """
    Fetch recent items (up to ~2 pages) and return raw result dicts.
    """
    items: List[Dict] = []
    base = dict(BASE_PARAMS)

    for page in (1, 2):
        params = dict(base)
        if page > 1:
            params["page"] = page
        data = call_api(params)
        results = data.get("results") or data.get("data") or []
        if not results:
            break
        items.extend(results)
        if len(items) >= (limit * 2):
            break
        time.sleep(1.0)

    return items

# ========= Post building =========

def choose_image(r: Dict) -> Optional[str]:
    # Prefer image_url; fallback to any plausible field
    cand = r.get("image_url") or r.get("image") or r.get("image_link")
    if cand and cand.lower().startswith(("http://", "https://")):
        return cand
    return None

def build_post_md(item: Dict) -> Optional[str]:
    """
    Turn a raw Newsdata item into a Markdown string (with YAML front matter).
    Returns None if fails quality gates.
    """
    title = (item.get("title") or "").strip()
    link = (item.get("link") or "").strip()
    desc = strip_html(item.get("description") or item.get("content") or "")
    title = title.replace("\n", " ").strip()

    if not title or not link or not desc:
        return None
    if not text_quality_ok(title, desc):
        return None

    # Keep recent only
    pub = parse_pubdate(item.get("pubDate"))
    if not pub:
        pub = now_utc()
    if (now_utc() - pub).total_seconds() > RECENT_WINDOW_HOURS * 3600:
        return None

    image = choose_image(item)
    excerpt = safe_excerpt(desc, 60)
    source_id = item.get("source_id") or ""

    # YAML front matter
    fm = [
        "---",
        'layout: post',
        f'title: "{title.replace(\'"\', \'\\\"\')}"',
        f"date: {pub.date().isoformat()}",
    ]
    if image:
        fm.append(f'image: "{image}"')
    if source_id:
        fm.append(f"source: {source_id}")
    fm.extend([
        "tags: [ai, news]",
        "---",
    ])

    body_parts = []
    if image:
        body_parts.append(f'![{title}]({image})\n')

    body_parts.append(excerpt + "\n")
    body_parts.append(f"\nSource: [{source_id or 'source'}]({link})\n")

    return "\n".join(fm) + "\n\n" + "\n".join(body_parts).strip() + "\n"

def save_post_md(title: str, pub: dt.datetime, content: str) -> Path:
    slug = slugify(title)[:60] or "post"
    filename = f"{pub.date().isoformat()}-{slug}.md"
    path = POSTS_DIR / filename
    # Avoid overwriting by suffixing number if exists
    i = 2
    while path.exists():
        path = POSTS_DIR / f"{pub.date().isoformat()}-{slug}-{i}.md"
        i += 1
    path.write_text(content, encoding="utf-8")
    return path

# ========= Main pipeline =========

def main() -> None:
    print("🧠 Fetching latest AI articles...")
    raw_items = fetch_latest(limit=MAX_POSTS)

    existing_titles, existing_links = load_existing_titles_and_links()

    created = 0
    for r in raw_items:
        if created >= MAX_POSTS:
            break

        title = (r.get("title") or "").strip()
        link = (r.get("link") or "").strip()
        if not title or not link:
            continue
        if title in existing_titles or link in existing_links:
            continue

        # Build content (also re-parses pubDate)
        pub = parse_pubdate(r.get("pubDate")) or now_utc()
        md = build_post_md(r)
        if not md:
            continue

        save_post_md(title, pub, md)
        created += 1
        print(f"✅ Created post: {title}")

    if created == 0:
        print("ℹ️ No qualifying new posts found.")
    else:
        print(f"🎉 Done. Created {created} post(s).")


if __name__ == "__main__":
    main()
