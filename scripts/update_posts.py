#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Update posts from Newsdata.io, with quality filters.

ENV:
  NEWS_API_KEY  -> your Newsdata API key (already set in Actions)

Behavior:
- Fetches page 1 only (avoids 422 pagination errors on free tier)
- Keeps at most MAX_POSTS good items
- Skips low-value or off-topic items
- Falls back to description when content is missing
"""

import os
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import requests
from slugify import slugify

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")

# ----- Tuning -----
MAX_POSTS = 5  # how many posts to create per run

# Topics we want
KEYWORDS = [
    "artificial intelligence",
    "ai",
    "machine learning",
    "openai",
    "anthropic",
    "llm",
    "google ai",
    "meta ai",
    "generative ai",
]

# Things to avoid (sports schedules, gossip, obvious off-topic)
BLACKLIST = [
    "bundesliga", "premier league", "rangers", "celtic", "championship",
    "derbies", "broadcasts", "lineup", "fixture", "kickoff", "highlights",
    "gossip", "soap opera", "celebrity", "transfer rumor",
]

# Strings that signal the item is paywalled/empty
PAYWALL_STRINGS = [
    "ONLY AVAILABLE IN PAID PLANS",
    "subscribe to read",
    "subscription required",
]

POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(parents=True, exist_ok=True)


def call_api(params: dict) -> dict:
    """Call Newsdata and raise nicely if the request fails."""
    resp = requests.get(API_URL, params=params, timeout=30)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        # show URL in logs if something goes wrong
        print("URL:", resp.url)
        raise
    return resp.json()


def fetch_latest(limit: int = MAX_POSTS) -> list[dict]:
    """
    Fetch recent AI/tech news (first page only).
    We request the first page only to avoid the "UnsupportedFilter" 422
    that happens with invalid pagination tokens on free plans.
    """
    if not API_KEY:
        raise RuntimeError("NEWS_API_KEY is missing in the environment.")

    query = " OR ".join(KEYWORDS)
    params = {
        "apikey": API_KEY,
        "q": query,
        "language": "en",
        "category": "technology",
        "page": 1,  # first page only — safe for free plan
    }

    print("🧠 Fetching latest AI articles...")
    data = call_api(params)

    if data.get("status") != "success":
        # Defensive: sometimes API returns error payload with 200 OK
        msg = data.get("results", {}).get("message") if isinstance(data.get("results"), dict) else data
        raise RuntimeError(f"API returned non-success status: {msg}")

    results = data.get("results") or []
    items: list[dict] = []
    for it in results:
        # Normalize fields we care about
        item = {
            "title": (it.get("title") or "").strip(),
            "description": (it.get("description") or "").strip(),
            "content": (it.get("content") or "").strip(),
            "link": it.get("link") or it.get("source_url") or "",
            "source": it.get("source_id") or it.get("source") or "source",
            "image": it.get("image_url") or "",
            "date": (it.get("pubDate") or it.get("pub_date") or ""),
        }
        items.append(item)

    # Filter, score, and take the best
    good = [it for it in items if is_good_item(it)]
    return good[:limit]


def is_blacklisted(text: str) -> bool:
    lo = text.lower()
    return any(b in lo for b in BLACKLIST)


def is_paywalled(text: str) -> bool:
    up = text.upper()
    return any(pw in up for pw in PAYWALL_STRINGS)


def body_from_item(item: dict) -> str:
    """Choose the best available body text."""
    body = item.get("content") or item.get("description") or ""
    # Remove boilerplate whitespace
    body = re.sub(r"\s+", " ", body).strip()
    return body


def is_good_item(item: dict) -> bool:
    """Quality filter for items."""
    title = item.get("title", "").strip()
    if not title or len(title) < 10:
        return False

    if is_blacklisted(title):
        return False

    body = body_from_item(item)
    if not body or len(body) < 180:  # ~2–3 sentences minimum
        return False
    if is_paywalled(body):
        return False

    # Also check the description for blacklist/paywall—sometimes content is blank but desc is bad
    desc = (item.get("description") or "").strip()
    if desc:
        if is_blacklisted(desc) or is_paywalled(desc):
            return False

    return True


def safe_excerpt(text: str, words: int = 40) -> str:
    """Plain excerpt limited by words."""
    tokens = re.split(r"\s+", text.strip())
    cut = " ".join(tokens[:words]).strip()
    return cut + ("…" if len(tokens) > words else "")


def parse_date(d: str) -> str:
    """
    Return YYYY-MM-DD. Newsdata dates are often RFC3339.
    """
    if not d:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        # Handles e.g. "2025-09-02 10:31:44", "2025-09-02T10:31:44Z", etc.
        d = d.replace("Z", "+00:00").replace(" ", "T") if "T" not in d else d
        dt = datetime.fromisoformat(d)
    except Exception:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d")


def build_markdown(item: dict) -> tuple[str, str]:
    """Create filename + markdown contents with front matter."""
    title = item["title"]
    slug = slugify(title)[:80] or "post"
    date_str = parse_date(item.get("date"))
    fname = f"{date_str}-{slug}.md"

    body = body_from_item(item)
    excerpt = safe_excerpt(body, 55)

    # Minimal formatting for readability
    wrapped = "\n\n".join(textwrap.fill(p, width=90) for p in re.split(r"\n{2,}|\.\s{1,}", body) if p.strip())

    # Front matter + body
    fm = [
        "---",
        f'title: "{title.replace("\\\"", "\\\\\\"")}"',
        f"date: {date_str}",
        f"excerpt: \"{excerpt.replace('\"', '\\\"')}\"",
        "layout: post",
    ]
    if item.get("image"):
        fm.append(f'image: "{item["image"]}"')
    fm.append("---")

    content = "\n".join(fm) + "\n\n"
    content += f"Source: [{item['source']}]({item['link']})\n\n"
    content += wrapped or excerpt  # guaranteed not empty by filters

    return fname, content


def write_post(filename: str, content: str) -> None:
    path = POSTS_DIR / filename
    if path.exists():
        print(f"— Skipping (already exists): {filename}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"✅ Created: {filename}")


def main():
    raw_items = fetch_latest(limit=MAX_POSTS)
    if not raw_items:
        print("⚠️ No suitable articles today (filters may have removed all).")
        return

    for it in raw_items:
        filename, md = build_markdown(it)
        write_post(filename, md)


if __name__ == "__main__":
    main()
