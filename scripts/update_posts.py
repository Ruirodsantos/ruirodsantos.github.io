#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fetch AI news from newsdata.io and create Jekyll posts in _posts/.
- Uses short queries to avoid 'UnsupportedQueryLength'
- Filters low-quality / irrelevant items
- ALWAYS writes a body paragraph (no blank posts)
- OVERWRITES today's post file if it already exists (so we can fix older empties)
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

MAX_POSTS = 5  # limit per run

# short, safe terms — each queried separately
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

# block obvious non-AI/low-value items
BLOCK_WORDS = [
    "premier league", "bundesliga", "rangers", "celtic", "brighton",
    "manchester city", "guardiola", "derbies",
    "tacos",
    "only available in paid plans",
]

MIN_TITLE_LEN = 12
MIN_EXCERPT_LEN = 40


# ========================
# Helpers
# ========================

def log(msg: str) -> None:
    print(msg, flush=True)


def ensure_api() -> None:
    if not API_KEY:
        raise ValueError("❌ NEWS_API_KEY não definida (Settings → Secrets and variables → Actions).")


def today_str() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


def clean(text: Optional[str]) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    t = t.replace("“", '"').replace("”", '"').replace("’", "'")
    return t


def is_good(title: str, excerpt: str, content: str) -> bool:
    t = title.lower()
    e = (excerpt or "").lower()
    c = (content or "").lower()

    if len(title) < MIN_TITLE_LEN:
        return False

    all_text = " ".join([t, e, c])
    for w in BLOCK_WORDS:
        if w in all_text:
            return False

    if len(excerpt) < MIN_EXCERPT_LEN and len(content) < MIN_EXCERPT_LEN:
        return False

    return True


def choose_image(item: Dict[str, Any]) -> Optional[str]:
    for k in ("image_url", "image", "thumbnail", "image_link"):
        v = item.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def call_api(params: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.get(API_URL, params=params, timeout=20)
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        log(f"❌ API error body: {r.text}")
        raise e
    data = r.json()
    if isinstance(data, dict) and data.get("status") == "error":
        log(f"⚠️ API status error: {json.dumps(data)}")
        raise requests.HTTPError(data)
    return data


def build_queries() -> List[str]:
    return AI_QUERY_TERMS[:]


def first_sentence(text: str, limit: int = 220) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    if parts and len(parts[0]) < limit:
        return parts[0]
    return text[:limit].rstrip() + "…"


def yaml_front_matter(meta: Dict[str, Any]) -> str:
    lines = ["---"]
    for k in ("layout", "title", "date", "excerpt", "image", "source", "link"):
        v = meta.get(k)
        if v is None or v == "":
            continue
        if isinstance(v, str):
            v = v.replace('"', '\\"')
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def safe_body(title: str, description: str, content: str, source: str) -> str:
    """
    Always return a non-empty body.
    Priority: content -> description -> neutral fallback based on title.
    """
    body = content or description
    if body:
        return body.strip()
    src = source or "the source"
    return f"This article titled “{title}” was reported by {src}. Details were not provided by the feed, so we’ve included the headline and source link for quick reference."


def write_post(item: Dict[str, Any]) -> Optional[str]:
    title = clean(item.get("title"))
    description = clean(item.get("description"))
    content = clean(item.get("content"))  # may be empty
    link = clean(item.get("link") or item.get("url") or "")
    source = clean(item.get("source_id") or item.get("source") or "")

    # quality filter
    if not is_good(title, description, content):
        return None

    date_str = today_str()
    slug = slugify(title)[:80] or "ai-news"
    path = f"{POSTS_DIR}/{date_str}-{slug}.md"

    # Build metadata + body (never empty)
    body_text = safe_body(title, description, content, source)
    excerpt = first_sentence(description or content or body_text, 220)
    meta = {
        "layout": "post",
        "title": title,
        "date": date_str,
        "excerpt": excerpt,
        "image": choose_image(item) or "",
        "source": source,
        "link": link,
    }
    fm = yaml_front_matter(meta)

    source_line = ""
    if source and link:
        source_line = f"\n\nSource: [{source}]({link})"
    elif link:
        source_line = f"\n\n[Read more]({link})"

    md = f"{fm}\n\n{body_text}{source_line}\n"

    # OVERWRITE today's file if it already exists to fix empty posts
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    return path


def fetch_latest(max_posts: int = MAX_POSTS) -> List[Dict[str, Any]]:
    ensure_api()
    log("📰 Fetching latest AI articles...")

    accepted: List[Dict[str, Any]] = []
    seen_links = set()

    for q in build_queries():
        if len(accepted) >= max_posts:
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
            if len(accepted) >= max_posts:
                break

            link = clean(it.get("link") or it.get("url") or "")
            if link and link in seen_links:
                continue

            title = clean(it.get("title"))
            desc = clean(it.get("description"))
            content = clean(it.get("content")) or ""

            if not is_good(title, desc, content):
                continue

            accepted.append(it)
            if link:
                seen_links.add(link)

        time.sleep(0.35)  # be polite to the API

    return accepted[:max_posts]


def main() -> None:
    try:
        items = fetch_latest(MAX_POSTS)
        if not items:
            log("ℹ️ No qualifying items found.")
            return

        created = 0
        for item in items:
            p = write_post(item)
            if p:
                created += 1
                log(f"✅ Post escrito: {p}")

        if created == 0:
            log("ℹ️ Nothing to write (filtered).")

    except Exception as e:
        log(f"❌ Falha: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
