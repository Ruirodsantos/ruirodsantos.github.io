#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-fetch AI news from Newsdata and create Jekyll posts.
- Splits queries into short variants to avoid 422 'UnsupportedQueryLength'
- Filters low-quality / irrelevant items
- Writes Markdown files into _posts/

Env:
  NEWS_API_KEY   -> your newsdata.io API key (public key is fine)
"""

import os
import re
import time
import json
import datetime as dt
from typing import List, Dict, Any, Optional

import requests
from slugify import slugify


# ========================
# Configuration
# ========================

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")

POSTS_DIR = "_posts"
os.makedirs(POSTS_DIR, exist_ok=True)

# How many good posts per run
MAX_POSTS = 5

# Short, safe search terms (each is sent separately)
AI_QUERY_TERMS: List[str] = [
    "ai",
    "artificial intelligence",
    "openai",
    "anthropic",
    "llm",
    "deepmind",
    "google ai",
    "meta ai",
    "microsoft ai",
    "nvidia ai",
    "apple ai",
]

# Filters (lowercased) for obvious non-AI content we saw popping up
BLOCK_WORDS = [
    "premier league",
    "bundesliga",
    "rangers",
    "celtic",
    "brighton",
    "manchester city",
    "guardiola",
    "derbies",
    "bundesliga on of",
    "tacos",  # drive-thru viral
    "only available in paid plans",
]

# Minimal text lengths
MIN_TITLE_LEN = 12
MIN_EXCERPT_LEN = 40

# ========================
# Helpers
# ========================

def log(msg: str) -> None:
    print(msg, flush=True)


def api_key_or_die() -> None:
    if not API_KEY:
        raise ValueError("❌ API_KEY não encontrada. Define o secret NEWS_API_KEY em Settings → Secrets and variables → Actions.")


def utc_date_str() -> str:
    # Jekyll expects YYYY-MM-DD
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


def sanitize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    # remove excessive whitespace and strange chars
    t = re.sub(r"\s+", " ", text).strip()
    # collapse quotes safely (no gymnastics inside f-strings)
    t = t.replace("“", '"').replace("”", '"').replace("’", "'")
    return t


def good_quality(title: str, excerpt: str, content: str) -> bool:
    t = title.lower()
    e = (excerpt or "").lower()
    c = (content or "").lower()

    if len(title) < MIN_TITLE_LEN:
        return False

    # discard items with the “paid plan” message or blocked topics
    all_text = " ".join([t, e, c])
    for w in BLOCK_WORDS:
        if w in all_text:
            return False

    # very short preview? likely useless
    if len(excerpt) < MIN_EXCERPT_LEN and len(content) < MIN_EXCERPT_LEN:
        return False

    return True


def choose_image(item: Dict[str, Any]) -> Optional[str]:
    """
    Newsdata can return different fields; try a few common ones.
    """
    for key in ("image_url", "image", "thumbnail", "image_link"):
        val = item.get(key)
        if val and isinstance(val, str) and val.startswith("http"):
            return val
    return None


def call_api(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a single API call; raise on HTTP errors with useful info.
    """
    r = requests.get(API_URL, params=params, timeout=20)
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        log(f"❌ API error: {r.text}")
        raise e
    data = r.json()
    # Newsdata may return {'status':'error', 'results': {'message': '...'}}
    if isinstance(data, dict) and data.get("status") == "error":
        log(f"⚠️ API error (422): {json.dumps(data)}")
        raise requests.HTTPError(data)
    return data


def build_queries() -> List[str]:
    """
    Return short queries to avoid 'Query length cannot be greater than 100'.
    We search each term separately and then merge results.
    """
    return AI_QUERY_TERMS[:]  # copy


def take_first_sentence(text: str, limit: int = 220) -> str:
    if not text:
        return ""
    # try to cut on sentence end, otherwise trim
    parts = re.split(r"(?<=[.!?])\s+", text)
    if parts:
        s = parts[0]
        if len(s) < limit:
            return s
    return text[:limit].rstrip() + "…"


def md_front_matter(meta: Dict[str, Any]) -> str:
    """
    Assemble YAML front matter safely (no f-string replacements for quotes).
    """
    lines = ["---"]
    for k in ("layout", "title", "date", "excerpt", "image", "source", "link"):
        v = meta.get(k)
        if v is None or v == "":
            continue
        if isinstance(v, str):
            # escape quotes for YAML safety
            v = v.replace('"', '\\"')
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def write_post(item: Dict[str, Any]) -> Optional[str]:
    """
    Create a Jekyll Markdown file for one news item.
    Returns the file path or None if skipped.
    """
    title = sanitize_text(item.get("title"))
    desc = sanitize_text(item.get("description"))
    content = sanitize_text(item.get("content")) or desc
    if not good_quality(title, desc, content):
        return None

    date_str = utc_date_str()
    slug = slugify(title)[:80] or "ai-news"
    filename = f"{POSTS_DIR}/{date_str}-{slug}.md"

    if os.path.exists(filename):
        # avoid duplicates (same day + same title)
        return None

    # Basic excerpt (first sentence or trims)
    excerpt = take_first_sentence(desc or content, 220)

    meta = {
        "layout": "post",
        "title": title,
        "date": date_str,
        "excerpt": excerpt,
        "image": choose_image(item) or "",
        "source": sanitize_text(item.get("source_id") or item.get("source") or ""),
        "link": sanitize_text(item.get("link") or item.get("url") or ""),
    }

    fm = md_front_matter(meta)
    body_lines = []

    # If we have longer content, show a compact version
    if content and content.lower() != meta["excerpt"].lower():
        body_lines.append(content)

    body_lines.append("")
    body_lines.append(f"Source: [{meta['source']}]({meta['link']})" if meta.get("source") else f"[Read more]({meta.get('link','')})")

    md = fm + "\n\n" + "\n".join(body_lines).strip() + "\n"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(md)

    return filename


# ========================
# Main fetching routine
# ========================

def fetch_latest(max_items: int = MAX_POSTS) -> List[Dict[str, Any]]:
    """
    Loop over short queries and merge the best items until we have max_items.
    """
    api_key_or_die()
    queries = build_queries()

    accepted: List[Dict[str, Any]] = []
    seen_links = set()

    log("📰 Fetching latest AI articles...")

    for q in queries:
        if len(accepted) >= max_items:
            break

        params = {
            "apikey": API_KEY,
            "q": q,
            "language": "en",
            "category": "technology",
        }

        try:
            data = call_api(params)
        except Exception as e:
            log(f"⚠️ Skipping query '{q}': {e}")
            continue

        results = data.get("results") or []
        for it in results:
            if len(accepted) >= max_items:
                break

            link = sanitize_text(it.get("link") or it.get("url") or "")
            if link in seen_links:
                continue

            title = sanitize_text(it.get("title"))
            desc = sanitize_text(it.get("description"))
            content = sanitize_text(it.get("content")) or desc

            if not good_quality(title, desc, content):
                continue

            accepted.append(it)
            seen_links.add(link)

        # Small delay to be nice with the API
        time.sleep(0.4)

    return accepted[:max_items]


def main() -> None:
    try:
        items = fetch_latest(MAX_POSTS)
        if not items:
            log("ℹ️ No qualifying items found.")
            return

        created = 0
        for it in items:
            path = write_post(it)
            if path:
                created += 1
                log(f"✅ Post criado: {path}")

        if created == 0:
            log("ℹ️ Nothing new to write (duplicates/filtered).")

    except Exception as e:
        log(f"❌ Falha: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
