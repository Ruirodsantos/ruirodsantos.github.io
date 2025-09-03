#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate daily AI blog posts from Newsdata.io

Environment:
  - NEWS_API_KEY (preferred) or NEWSDATA_API_KEY

Behavior:
  - Fetches recent AI news
  - Filters out low-quality or off-topic items
  - Expands short items into readable summaries
  - Creates up to MAX_POSTS markdown files in _posts/
"""

import os
import re
import json
import time
import datetime as dt
from typing import Dict, List, Optional

import requests
from slugify import slugify

# --------------------------- Configuration -------------------------------- #

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY") or os.getenv("NEWSDATA_API_KEY")

POSTS_DIR = "_posts"
MAX_POSTS = 5

# Query — keep broad but relevant
QUERY = (
    "artificial intelligence OR ai OR machine learning OR generative ai "
    "OR openai OR anthropic OR google ai OR meta ai OR llm"
)

# Language/category – keep simple to avoid 422s from the API
BASE_PARAMS = {
    "q": QUERY,
    "language": "en",
    "category": "technology",
    "page": 1,
}

# Quality filters
MIN_DESC_WORDS = 20
BANNED_PHRASES = {
    "only available in paid plans",
    "subscription required",
    "subscribe to read",
}
# Obvious off-topic filters (you can expand this list any time)
OFFTOPIC_PATTERNS = re.compile(
    r"\b(football|soccer|bundesliga|premier league|nfl|nba|mlb|tennis|f1|cricket|match|fixture)\b",
    re.IGNORECASE,
)

# -------------------------------------------------------------------------- #


def fail(msg: str) -> None:
    print(f"❌ {msg}")
    raise SystemExit(1)


def log(msg: str) -> None:
    print(f"🧠 {msg}")


def ensure_api_key() -> None:
    if not API_KEY:
        fail("API_KEY not found. Set NEWS_API_KEY (or NEWSDATA_API_KEY) in repo variables/secrets.")


def ensure_posts_dir() -> None:
    os.makedirs(POSTS_DIR, exist_ok=True)


def call_api(params: Dict) -> Dict:
    """Call Newsdata.io and return JSON, raising on HTTP errors."""
    url = API_URL
    p = dict(params)
    p["apikey"] = API_KEY

    resp = requests.get(url, params=p, timeout=30)
    # Show a helpful message if the API returns 422 (common for invalid combos)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        log(f"API error ({resp.status_code}): {resp.text[:300]}")
        raise
    data = resp.json()
    return data


def fetch_latest(limit: int = MAX_POSTS) -> List[Dict]:
    """
    Fetch a few fresh items. Keep the request simple:
    - no date filters (Newsdata 422s easily with tight filters)
    """
    items: List[Dict] = []
    params = dict(BASE_PARAMS)

    # We’ll try up to 2 pages to collect enough items
    for page in (1, 2):
        params["page"] = page
        data = call_api(params)
        results = data.get("results") or data.get("data") or []
        if not results:
            break
        items.extend(results)
        if len(items) >= limit:
            break

        # be nice to the API
        time.sleep(1.0)

    return items[:limit * 2]  # return a bit more for filtering headroom


def is_offtopic(title: str, desc: str) -> bool:
    text = f"{title} {desc}"
    return bool(OFFTOPIC_PATTERNS.search(text))


def bad_content(title: str, desc: str, content: str) -> bool:
    """Return True if the item is obviously low-quality/junk."""
    if not title.strip():
        return True
    if desc and title.strip().lower() == desc.strip().lower():
        return True
    if len((desc or "").split()) < MIN_DESC_WORDS:
        return True
    joined = " ".join([title, desc or "", content or ""]).lower()
    if any(ph in joined for ph in BANNED_PHRASES):
        return True
    return False


def expand_text(title: str, desc: str, source: Optional[str]) -> str:
    """
    Create a readable 2–3 paragraph summary using only local heuristics.
    This avoids external AI calls (safe inside Actions).
    """
    clean_title = title.strip().rstrip(".")
    clean_desc = (desc or "").strip()

    p1 = clean_desc

    p2 = (
        f"This update around **{clean_title}** reflects a broader trend in the rapid adoption "
        f"of artificial intelligence across industries. Analysts note that developments like "
        f"these often influence investment priorities, product roadmaps, and the competitive "
        f"landscape for both startups and large platforms."
    )

    src_part = f" the original source ({source})" if source else " the original source"
    p3 = (
        f"For readers following AI closely, the key takeaways are practical: watch for follow-up "
        f"announcements, early pilot programs, and measurable outcomes over the next few quarters. "
        f"More details may emerge as organizations publish technical posts, earnings notes, or third-party reviews at{src_part}."
    )

    return f"{p1}\n\n{p2}\n\n{p3}"


def unique_filepath(date: dt.date, title: str) -> str:
    base_slug = slugify(title)[:60] or f"post-{int(time.time())}"
    fname = f"{date.isoformat()}-{base_slug}.md"
    path = os.path.join(POSTS_DIR, fname)

    # Avoid overwriting if file exists
    if not os.path.exists(path):
        return path

    # Add a short counter suffix
    for i in range(2, 100):
        alt = os.path.join(POSTS_DIR, f"{date.isoformat()}-{base_slug}-{i}.md")
        if not os.path.exists(alt):
            return alt

    # Fallback (extremely unlikely)
    return os.path.join(POSTS_DIR, f"{date.isoformat()}-{base_slug}-{int(time.time())}.md")


def build_markdown(article: Dict) -> Optional[str]:
    """
    Return the markdown string for a valid article, or None if it should be skipped.
    """
    title = (article.get("title") or "").strip()
    desc = (article.get("description") or "").strip()
    content = (article.get("content") or "").strip()
    link = article.get("link") or article.get("url") or ""
    source = article.get("source_id") or (article.get("source") or {}).get("name") or ""
    image = article.get("image_url") or article.get("image")

    if is_offtopic(title, desc):
        return None
    if bad_content(title, desc, content):
        return None

    # Expand thin content if needed
    if not content or len(content) < 300:
        content = expand_text(title, desc, link)

    # Front matter
    today = dt.date.today()
    fm = {
        "layout": "post",
        "title": title.replace('"', "'"),
        "date": today.isoformat(),
        "excerpt": (desc or "").replace('"', "'"),
        "categories": ["ai", "news"],
    }
    if image:
        fm["image"] = image

    # Build markdown
    front_matter = (
        "---\n" + "\n".join(
            [
                f'layout: {fm["layout"]}',
                f'title: "{fm["title"]}"',
                f'date: {fm["date"]}',
                f'excerpt: "{fm["excerpt"]}"',
                "categories: [ai, news]",
            ]
            + ([f"image: {image}"] if image else [])
        ) + "\n---\n\n"
    )

    body_parts = []
    if link or source:
        src_line = f"Source: [{source or 'link'}]({link})" if link else f"Source: {source}"
        body_parts.append(src_line)
        body_parts.append("")  # blank line

    body_parts.append(content.strip())

    md = front_matter + "\n".join(body_parts).strip() + "\n"
    return md


def main() -> None:
    ensure_api_key()
    ensure_posts_dir()

    log("Fetching latest AI articles…")
    raw_items = fetch_latest(limit=MAX_POSTS)

    if not raw_items:
        fail("No items returned by the API.")

    created = 0
    today = dt.date.today()

    for art in raw_items:
        md = build_markdown(art)
        if not md:
            continue

        path = unique_filepath(today, art.get("title", "untitled"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)

        created += 1
        log(f"✅ Created: {os.path.basename(path)}")

        if created >= MAX_POSTS:
            break

    if created == 0:
        fail("No high-quality articles to publish today (all filtered).")
    else:
        log(f"🎉 Done. {created} post(s) created in '{POSTS_DIR}'.")


if __name__ == "__main__":
    main()
